from fastapi import APIRouter, HTTPException, Request
from config import settings
from pydantic import BaseModel, Field


class ModeRequest(BaseModel):
    mode: str = Field(..., pattern="^(idle|match|training|challenge)$")


class TrainingLevelRequest(BaseModel):
    level: int = Field(..., ge=1, le=10)


class PlacementRequest(BaseModel):
    cue_pos: list = Field(..., min_length=2, max_length=2)
    target_pos: list = Field(..., min_length=2, max_length=2)


class ModelConfigRequest(BaseModel):
    condition_physics: bool = False


router = APIRouter(prefix="/api")

# Shared state - populated by main.py
system_state = {
    "camera": None,
    "table_detector": None,
    "ball_detector": None,
    "physics": None,
    "match_mode": None,
    "training_mode": None,
    "current_mode": "idle",
    "table_state": {
        "detected": False,
        "balls": [],
    },
    "pocketed_balls": [],  # persisted across session for refresh/reconnect sync
}

import threading
_system_state_lock = threading.Lock()


@router.get("/status")
async def get_status():
    return {
        "status": "running",
        "mode": system_state["current_mode"],
        "camera": system_state["camera"] is not None,
        "table_detected": system_state["table_state"]["detected"],
        "ball_count": len(system_state["table_state"]["balls"]),
    }


@router.get("/table")
async def get_table():
    ts = system_state["table_state"]
    return {k: v for k, v in ts.items() if k != "ball_objects"}


@router.get("/table/view")
async def get_table_view():
    """Get simplified table overhead view data for phone app."""
    balls = system_state.get("table_state", {}).get("balls", [])
    table = system_state.get("table_state", {})
    return {
        "detected": table.get("detected", False),
        "ball_count": len(balls),
        "cue_speed": table.get("last_cue_speed", 0),
        "balls": [
            {
                "x": float(b.get("x", 0)),
                "y": float(b.get("y", 0)),
                "type": "cue" if b.get("is_cue") else
                        "black" if b.get("is_black") else
                        "solid" if b.get("is_solid") else "stripe",
                "color": b.get("color", ""),
            }
            for b in balls
        ],
    }


@router.post("/mode")
async def set_mode(req: ModeRequest):
    system_state["current_mode"] = req.mode
    if req.mode == "match" and system_state.get("match_mode"):
        system_state["match_mode"].start_new_match()
    if req.mode == "challenge" and system_state.get("training_mode"):
        info = system_state["training_mode"].start_challenge()
        return {"mode": req.mode, "info": info}
    if req.mode == "training" and system_state.get("training_mode"):
        # Training mode: all levels accessible, not challenge-locked
        tm = system_state["training_mode"]
        tm.session.challenge_mode = False
        return {"mode": req.mode, "info": "Select a level"}
    return {"mode": req.mode}


@router.post("/control/start")
async def start_system():
    system_state["current_mode"] = "idle"
    return {"status": "started"}


@router.post("/control/stop")
async def stop_system():
    system_state["current_mode"] = "idle"
    return {"status": "stopped"}


@router.get("/score")
async def get_score():
    mm = system_state.get("match_mode")
    if not mm:
        return {"error": "Match mode not initialized"}
    s = mm.state
    return {
        "player1_score": s.player1_score,
        "player2_score": s.player2_score,
        "current_player": s.current_player,
        "game_over": s.game_over,
        "winner": s.winner,
    }


@router.get("/training/levels")
async def get_training_levels():
    from game.training_data import get_all_levels
    levels = get_all_levels()
    return [
        {
            "level": lv.level,
            "name": lv.name,
            "description": lv.description,
            "drill_count": len(lv.drills),
        }
        for lv in levels
    ]


@router.post("/training/select-level")
async def select_training_level(req: TrainingLevelRequest):
    tm = system_state.get("training_mode")
    if not tm:
        raise HTTPException(400, "Training mode not initialized")
    result = tm.select_level(req.level)
    if "error" in result:
        raise HTTPException(400, result["error"])
    # Broadcast drill info via WebSocket to phone clients
    from .websocket import manager
    import asyncio
    asyncio.create_task(manager.broadcast_drill_info(result))
    return result


@router.post("/training/verify-placement")
async def verify_placement(req: PlacementRequest):
    tm = system_state.get("training_mode")
    if not tm:
        raise HTTPException(400, "Training mode not initialized")
    return tm.verify_placement(tuple(req.cue_pos), tuple(req.target_pos))


from fastapi import WebSocket, WebSocketDisconnect
from .websocket import manager


@router.post("/calibration/start")
async def start_calibration():
    system_state["calibration"] = {
        "active": True,
        "markers": [],
        "table_detected": False,
        "status": "Calibration starting...",
    }
    return {"status": "calibration_started"}


@router.post("/calibration/stop")
async def stop_calibration():
    cal = system_state.get("calibration", {})
    cal["active"] = False
    return {"status": "calibration_stopped"}


@router.get("/calibration/status")
async def get_calibration_status():
    return system_state.get("calibration", {"active": False})


@router.post("/ai-train/start")
async def start_ai_train():
    """开始AI训练：投影逐个显示标准击球位置，用户击球采集数据"""
    if not system_state.get("training_mode"):
        raise HTTPException(400, "Training mode not initialized")
    tm = system_state["training_mode"]
    tm.session.challenge_mode = False
    system_state["ai_training"] = {
        "active": True,
        "drill_index": 0,
        "total_drills": 10,
        "status": "AI训练中",
    }
    return {"status": "ai_training_started", "total": 10}


@router.post("/ai-train/stop")
async def stop_ai_train():
    train = system_state.get("ai_training", {})
    train["active"] = False
    return {"status": "ai_training_stopped"}


@router.get("/ai-train/status")
async def get_ai_train_status():
    return system_state.get("ai_training", {"active": False})


# ── Manual screenshot capture for ball ML ──

@router.post("/training/ball-ml/capture")
async def manual_capture_frame():
    """手动截取当前摄像头帧，保存到raw目录供后续标注"""
    import cv2
    import time
    cam = system_state.get("camera")
    if cam is None:
        raise HTTPException(503, "Camera not available")
    frame = cam.get_frame()
    if frame is None or not frame.valid or frame.data is None:
        raise HTTPException(503, "No valid frame from camera")
    raw_dir = _get_ball_raw_dir()
    ts = time.strftime("%Y%m%d_%H%M%S")
    fname = f"capture_{ts}.jpg"
    path = _os.path.join(raw_dir, fname)
    cv2.imwrite(path, frame.data, [cv2.IMWRITE_JPEG_QUALITY, 92])
    count = _count_files(raw_dir, ".jpg")
    return {"ok": True, "filename": fname, "raw_count": count}


@router.websocket("/ws/phone")
async def phone_websocket(ws: WebSocket):
    await manager.connect_phone(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


@router.websocket("/ws/projector")
async def projector_websocket(ws: WebSocket):
    await manager.connect_projector(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


@router.websocket("/ws/camera-preview")
async def camera_preview_websocket(ws: WebSocket):
    await manager.connect_camera_preview(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


@router.websocket("/ws/projector-preview")
async def projector_preview_websocket(ws: WebSocket):
    await manager.connect_projector_preview(ws)
    try:
        while True:
            await ws.receive_text()
    except WebSocketDisconnect:
        manager.disconnect(ws)


@router.websocket("/ws/camera-upload")
async def camera_upload_websocket(ws: WebSocket):
    await manager.connect_camera_upload(ws)


# ── Training Data Management ──

import os as _os
import json
import shutil
from config import settings as _settings


# ── Directory helpers ──

def _get_ball_ml_dir() -> str:
    d = _settings.BALL_ML_DATA_DIR
    _os.makedirs(d, exist_ok=True)
    return d

def _get_ball_raw_dir() -> str:
    d = _os.path.join(_get_ball_ml_dir(), "raw")
    _os.makedirs(d, exist_ok=True)
    return d

def _get_ball_annotated_img_dir() -> str:
    d = _os.path.join(_get_ball_ml_dir(), "images")
    _os.makedirs(d, exist_ok=True)
    return d

def _get_ball_annotated_label_dir() -> str:
    d = _os.path.join(_get_ball_ml_dir(), "labels")
    _os.makedirs(d, exist_ok=True)
    return d

def _get_ball_trained_dir() -> str:
    d = _os.path.join(_get_ball_ml_dir(), "trained")
    _os.makedirs(d, exist_ok=True)
    return d

def _get_traj_dir() -> str:
    d = _settings.TRAJECTORY_DATA_DIR
    _os.makedirs(d, exist_ok=True)
    return d

def _get_traj_new_dir() -> str:
    d = _os.path.join(_get_traj_dir(), "new")
    _os.makedirs(d, exist_ok=True)
    return d

def _get_traj_trained_dir() -> str:
    d = _os.path.join(_get_traj_dir(), "trained")
    _os.makedirs(d, exist_ok=True)
    return d

def _count_files(d: str, ext: str) -> int:
    if not _os.path.isdir(d):
        return 0
    return len([f for f in _os.listdir(d) if f.endswith(ext)])


def _dir_size_mb(d: str) -> float:
    """Total size of directory in MB, recursive."""
    if not _os.path.isdir(d):
        return 0.0
    total = 0
    for root, _, files in _os.walk(d):
        for f in files:
            try:
                total += _os.path.getsize(_os.path.join(root, f))
            except OSError:
                pass
    return total / (1024 * 1024)


# ── Config endpoints ──

@router.get("/config/training-dirs")
async def get_training_dirs():
    """获取训练数据目录状态（含各子目录文件数）"""
    raw_cnt = _count_files(_get_ball_raw_dir(), ".jpg")
    ann_img = _count_files(_get_ball_annotated_img_dir(), ".jpg")
    ann_lbl = _count_files(_get_ball_annotated_label_dir(), ".txt")
    trained_ball = _count_files(_get_ball_trained_dir(), ".jpg")
    traj_new_cnt = _count_files(_get_traj_new_dir(), ".json")
    traj_trained_cnt = _count_files(_get_traj_trained_dir(), ".json")

    return {
        "ball_ml_data_dir": _settings.BALL_ML_DATA_DIR,
        "ball_ml": {
            "raw": raw_cnt,
            "annotated_images": ann_img,
            "annotated_labels": ann_lbl,
            "trained": trained_ball,
            "total_size_mb": round(
                _dir_size_mb(_get_ball_ml_dir()), 2),
        },
        "trajectory_data_dir": _settings.TRAJECTORY_DATA_DIR,
        "trajectory": {
            "new": traj_new_cnt,
            "trained": traj_trained_cnt,
            "untrained": traj_new_cnt,
            "total_new_mb": round(_dir_size_mb(_get_traj_new_dir()), 2),
            "total_trained_mb": round(_dir_size_mb(_get_traj_trained_dir()), 2),
            "total_size_mb": round(_dir_size_mb(_get_traj_dir()), 2),
        },
    }


@router.post("/config/training-dirs")
async def set_training_dirs(req: Request):
    """修改训练数据存储目录"""
    body = await req.json()
    changed = []
    if "ball_ml_data_dir" in body:
        new_dir = str(body["ball_ml_data_dir"]).strip()
        if new_dir and _os.path.isabs(new_dir):
            _settings.BALL_ML_DATA_DIR = new_dir
            _os.makedirs(new_dir, exist_ok=True)
            changed.append("ball_ml_data_dir")
    if "trajectory_data_dir" in body:
        new_dir = str(body["trajectory_data_dir"]).strip()
        if new_dir and _os.path.isabs(new_dir):
            _settings.TRAJECTORY_DATA_DIR = new_dir
            _os.makedirs(new_dir, exist_ok=True)
            changed.append("trajectory_data_dir")
    return {"ok": True, "changed": changed, "ball_ml_data_dir": _settings.BALL_ML_DATA_DIR,
            "trajectory_data_dir": _settings.TRAJECTORY_DATA_DIR}


# ── Ball ML: dedup raw images ──

def _image_hash(path: str, thumb_size: int = 32) -> str:
    """Compute perceptual hash via downsample + grayscale."""
    import cv2
    img = cv2.imread(path, cv2.IMREAD_GRAYSCALE)
    if img is None:
        return ""
    thumb = cv2.resize(img, (thumb_size, thumb_size))
    avg = thumb.mean()
    bits = (thumb > avg).flatten()
    return ''.join('1' if b else '0' for b in bits)


def _hamming_distance(h1: str, h2: str) -> int:
    return sum(c1 != c2 for c1, c2 in zip(h1, h2))


@router.post("/training/ball-ml/dedup")
async def dedup_ball_raw():
    """对raw目录中的图片一键去重，保留每张有位置变化的图片"""
    raw_dir = _get_ball_raw_dir()
    files = sorted([
        f for f in _os.listdir(raw_dir)
        if f.endswith('.jpg') or f.endswith('.png')
    ])
    if len(files) < 2:
        return {"ok": True, "scanned": len(files), "removed": 0, "kept": len(files)}

    # Compute hashes
    hashes = {}
    for f in files:
        h = _image_hash(_os.path.join(raw_dir, f))
        if h:
            hashes[f] = h

    # Group by similarity (hamming distance <= 4 → ~94% similar on 256-bit hash)
    THRESHOLD = 4
    removed = []
    kept = list(hashes.keys())

    for i in range(len(files)):
        f1 = files[i]
        if f1 not in hashes or f1 in removed:
            continue
        for j in range(i + 1, len(files)):
            f2 = files[j]
            if f2 not in hashes or f2 in removed:
                continue
            dist = _hamming_distance(hashes[f1], hashes[f2])
            if dist <= THRESHOLD:
                # Keep the larger file (likely higher quality), remove the smaller
                s1 = _os.path.getsize(_os.path.join(raw_dir, f1))
                s2 = _os.path.getsize(_os.path.join(raw_dir, f2))
                if s1 >= s2:
                    _os.remove(_os.path.join(raw_dir, f2))
                    removed.append(f2)
                else:
                    _os.remove(_os.path.join(raw_dir, f1))
                    removed.append(f1)
                    break  # f1 removed, stop comparing

    kept = [f for f in files if f not in removed]
    return {
        "ok": True,
        "scanned": len(files),
        "removed": len(removed),
        "kept": len(kept),
        "removed_files": removed[:20],
    }


# ── Ball ML: move annotated → trained ──

@router.post("/training/ball-ml/archive-trained")
async def archive_ball_trained():
    """将已标注的图片和标签移动到trained目录（训练后归档）"""
    img_dir = _get_ball_annotated_img_dir()
    label_dir = _get_ball_annotated_label_dir()
    trained_dir = _get_ball_trained_dir()

    moved = 0
    for f in _os.listdir(img_dir):
        if f.endswith('.jpg'):
            base = f.rsplit('.', 1)[0]
            src_img = _os.path.join(img_dir, f)
            dst_img = _os.path.join(trained_dir, f)
            shutil.move(src_img, dst_img)
            # Move corresponding label
            for ext in ('.txt',):
                src_lbl = _os.path.join(label_dir, base + ext)
                if _os.path.exists(src_lbl):
                    shutil.move(src_lbl, _os.path.join(trained_dir, base + ext))
            moved += 1
    return {"ok": True, "moved": moved}


# ── Trajectory: move new → trained ──

@router.post("/training/trajectory/archive-trained")
async def archive_trajectory_trained():
    """将new目录中的击球数据移动到trained目录（训练后归档）"""
    new_dir = _get_traj_new_dir()
    trained_dir = _get_traj_trained_dir()
    moved = 0
    for f in _os.listdir(new_dir):
        if f.endswith('.json'):
            shutil.move(_os.path.join(new_dir, f), _os.path.join(trained_dir, f))
            moved += 1
    return {"ok": True, "moved": moved}


# ── Annotation API (for training data labeling) ──


def _resolve_safe_path(base_dir: str, name: str) -> str:
    """Resolve a safe path within base_dir, preventing traversal."""
    if '..' in name or '/' in name or '\\' in name:
        raise HTTPException(403, "Invalid filename")
    safe = _os.path.realpath(_os.path.join(base_dir, name))
    base_real = _os.path.realpath(base_dir)
    if not safe.startswith(base_real + _os.sep) and safe != base_real:
        raise HTTPException(403, "Access denied")
    return safe


@router.get("/annotate/images")
async def list_annotate_images():
    """列出已标注的图片（images目录）"""
    img_dir = _get_ball_annotated_img_dir()
    if not _os.path.isdir(img_dir):
        return []
    files = sorted([f for f in _os.listdir(img_dir) if f.endswith('.jpg')])
    return files


@router.get("/annotate/image/{name}")
async def get_annotate_image(name: str):
    from fastapi.responses import FileResponse
    path = _resolve_safe_path(_get_ball_annotated_img_dir(), name)
    if not _os.path.isfile(path):
        raise HTTPException(404, "Image not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/annotate/labels/{name}")
async def get_annotate_labels(name: str):
    from fastapi.responses import PlainTextResponse
    path = _resolve_safe_path(_get_ball_annotated_label_dir(), name)
    if not _os.path.isfile(path):
        return PlainTextResponse("", status_code=200)
    with open(path) as f:
        return PlainTextResponse(f.read())


@router.post("/annotate/save/{name}")
async def save_annotate_labels(name: str, req: Request):
    from fastapi.responses import PlainTextResponse
    label_dir = _get_ball_annotated_label_dir()
    body = await req.body()
    path = _resolve_safe_path(label_dir, name)
    text = body.decode('utf-8').strip()
    with open(path, 'w') as f:
        f.write(text if text else ' ')
    return PlainTextResponse("OK")
