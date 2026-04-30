from fastapi import APIRouter, HTTPException, Request
from typing import Optional
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
    return system_state["table_state"]


@router.post("/mode")
async def set_mode(req: ModeRequest):
    valid_modes = ["idle", "match", "training", "challenge"]
    if req.mode not in valid_modes:
        raise HTTPException(400, f"Invalid mode. Valid: {valid_modes}")
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
    asyncio.ensure_future(manager.broadcast_drill_info(result))
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


# ── Training Data Directory Config ──

import os as _os
from config import settings as _settings


def _get_ball_ml_dir() -> str:
    d = _settings.BALL_ML_DATA_DIR
    _os.makedirs(d, exist_ok=True)
    return d


def _get_ball_ml_img_dir() -> str:
    d = _os.path.join(_get_ball_ml_dir(), "images")
    _os.makedirs(d, exist_ok=True)
    return d


def _get_ball_ml_label_dir() -> str:
    d = _os.path.join(_get_ball_ml_dir(), "labels")
    _os.makedirs(d, exist_ok=True)
    return d


def _get_trajectory_dir() -> str:
    d = _settings.TRAJECTORY_DATA_DIR
    _os.makedirs(d, exist_ok=True)
    return d


@router.get("/config/training-dirs")
async def get_training_dirs():
    """获取训练数据存储目录配置"""
    return {
        "ball_ml_data_dir": _settings.BALL_ML_DATA_DIR,
        "ball_ml_img_count": len([
            f for f in _os.listdir(_get_ball_ml_img_dir())
            if f.endswith('.jpg')
        ]) if _os.path.isdir(_get_ball_ml_img_dir()) else 0,
        "trajectory_data_dir": _settings.TRAJECTORY_DATA_DIR,
        "trajectory_shot_count": len([
            f for f in _os.listdir(_get_trajectory_dir())
            if f.endswith('.json')
        ]) if _os.path.isdir(_get_trajectory_dir()) else 0,
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
    img_dir = _get_ball_ml_img_dir()
    if not _os.path.isdir(img_dir):
        return []
    files = sorted([f for f in _os.listdir(img_dir) if f.endswith('.jpg')])
    return files


@router.get("/annotate/image/{name}")
async def get_annotate_image(name: str):
    from fastapi.responses import FileResponse
    path = _resolve_safe_path(_get_ball_ml_img_dir(), name)
    if not _os.path.isfile(path):
        raise HTTPException(404, "Image not found")
    return FileResponse(path, media_type="image/jpeg")


@router.get("/annotate/labels/{name}")
async def get_annotate_labels(name: str):
    from fastapi.responses import PlainTextResponse
    path = _resolve_safe_path(_get_ball_ml_label_dir(), name)
    if not _os.path.isfile(path):
        return PlainTextResponse("", status_code=200)
    with open(path) as f:
        return PlainTextResponse(f.read())


@router.post("/annotate/save/{name}")
async def save_annotate_labels(name: str, req: Request):
    from fastapi.responses import PlainTextResponse
    label_dir = _get_ball_ml_label_dir()
    body = await req.body()
    path = _resolve_safe_path(label_dir, name)
    text = body.decode('utf-8').strip()
    with open(path, 'w') as f:
        f.write(text if text else ' ')
    return PlainTextResponse("OK")
