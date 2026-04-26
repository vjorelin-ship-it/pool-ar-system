from fastapi import APIRouter, HTTPException
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
    return result


@router.post("/training/verify-placement")
async def verify_placement(cue_pos: list, target_pos: list):
    tm = system_state.get("training_mode")
    if not tm:
        raise HTTPException(400, "Training mode not initialized")
    return tm.verify_placement(tuple(cue_pos), tuple(target_pos))


from fastapi import WebSocket
from .websocket import manager


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
