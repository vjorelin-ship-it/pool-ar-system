from fastapi import APIRouter, HTTPException, Request
from typing import Optional
from config import settings

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
async def set_mode(mode: str):
    valid_modes = ["idle", "match", "training", "challenge"]
    if mode not in valid_modes:
        raise HTTPException(400, f"Invalid mode. Valid: {valid_modes}")
    system_state["current_mode"] = mode
    if mode == "match" and system_state.get("match_mode"):
        system_state["match_mode"].start_new_match()
    if mode == "challenge" and system_state.get("training_mode"):
        info = system_state["training_mode"].start_challenge()
        return {"mode": mode, "info": info}
    if mode == "training" and system_state.get("training_mode"):
        # Training mode: all levels accessible, not challenge-locked
        tm = system_state["training_mode"]
        tm.session.challenge_mode = False
        return {"mode": mode, "info": "Select a level"}
    return {"mode": mode}


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
async def select_training_level(level: int):
    tm = system_state.get("training_mode")
    if not tm:
        raise HTTPException(400, "Training mode not initialized")
    result = tm.select_level(level)
    if "error" in result:
        raise HTTPException(400, result["error"])
    # Broadcast drill info via WebSocket to phone clients
    from .websocket import manager
    import asyncio
    asyncio.ensure_future(manager.broadcast_drill_info(result))
    return result


@router.post("/training/verify-placement")
async def verify_placement(cue_pos: list, target_pos: list):
    tm = system_state.get("training_mode")
    if not tm:
        raise HTTPException(400, "Training mode not initialized")
    return tm.verify_placement(tuple(cue_pos), tuple(target_pos))


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


# ── Model & Collector API ──

@router.get("/model/status")
async def get_model_status():
    """Get diffusion model status"""
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503, "System not initialized")
    return m.trajectory_model.get_status()


@router.post("/model/pretrain")
async def trigger_pretrain():
    """Trigger synthetic data pretraining (background thread)"""
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503, "System not initialized")
    from learning.synthetic_data import SyntheticDataGenerator
    gen = SyntheticDataGenerator(num_frames=m.trajectory_model.config["n_frames"])
    samples = gen.generate(num_samples=1000)  # 1000 for quick test, increase for production
    m.trajectory_model.train_async(samples, epochs=50, batch_size=8)
    return {"status": "started", "samples": len(samples)}


@router.post("/model/finetune")
async def trigger_finetune():
    """Trigger real data fine-tuning (background thread)"""
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503, "System not initialized")
    import os, json
    data_dir = os.path.join(os.path.dirname(__file__),
                            '..', 'learning', 'collected_shots')
    real_data = []
    if os.path.isdir(data_dir):
        for f in sorted(os.listdir(data_dir)):
            if f.endswith('.json'):
                with open(os.path.join(data_dir, f)) as fp:
                    real_data.append(json.load(fp))
    if len(real_data) < 10:
        raise HTTPException(400, f"Need at least 10 collected shots, have {len(real_data)}")
    m.trajectory_model.train_async(real_data, epochs=50, batch_size=8)
    return {"status": "started", "samples": len(real_data)}


@router.get("/model/config")
async def get_model_config():
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503)
    return {
        "condition_physics": m._use_ai_trajectory,
        "model_config": m.trajectory_model.config,
    }


@router.post("/model/config")
async def set_model_config(req: Request):
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503)
    body = await req.json()
    if "condition_physics" in body:
        m._use_ai_trajectory = bool(body["condition_physics"])
    return {"ok": True}


@router.get("/collector/status")
async def get_collector_status():
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503)
    c = m.trajectory_collector
    return {
        "collecting": c.is_collecting,
        "recording": c.is_recording,
        "total_collected": c.count(),
    }


@router.post("/collector/start")
async def start_collector():
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503)
    m.trajectory_collector.start()
    return {"status": "started"}


@router.post("/collector/stop")
async def stop_collector():
    m = system_state.get("main_system")
    if m is None:
        raise HTTPException(503)
    m.trajectory_collector.stop()
    return {"status": "stopped", "total": m.trajectory_collector.count()}
