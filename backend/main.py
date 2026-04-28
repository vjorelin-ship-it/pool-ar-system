import asyncio
import base64
import sys
import os
import json
import socket
import threading
import time
from typing import Optional

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from calibration_store import save_calibration, load_calibration, clear_calibration
from api.routes import router, system_state
from api.websocket import manager
from web.scoreboard_app import router as scoreboard_router
from camera.rtsp_camera import RtspCamera
from physics.engine import PhysicsEngine, Vec2
from game.match_mode import MatchMode
from game.training_mode import TrainingMode
from game.announcer import Announcer
from renderer.projector_renderer import ProjectorRenderer, ProjectionOverlay
from vision.table_detector import TableDetector
from vision.ball_detector import BallDetector
from vision.pocket_detector import PocketDetector
from vision.speed_detector import SpeedDetector
from learning.data_collector import DataCollector, ShotRecord
from learning.physics_adapter import PhysicsAdapter
from learning.correction_model import CorrectionModel
from learning.diffusion_model import DiffusionTrajectoryModel
from learning.trajectory_collector import TrajectoryCollector


class PoolARSystem:
    def __init__(self):
        self.camera: Optional[RtspCamera] = None
        self.table_detector = TableDetector()
        self.ball_detector = BallDetector()
        self.physics = PhysicsEngine()
        self.match_mode = MatchMode()
        self.training_mode = TrainingMode()
        self.renderer = ProjectorRenderer()
        self.pocket_detector = PocketDetector()
        self.speed_detector = SpeedDetector()
        self.announcer = Announcer()
        self.data_collector = DataCollector()
        self.physics_adapter = PhysicsAdapter()
        self.correction_model = CorrectionModel()
        # Diffusion trajectory model
        self.trajectory_model = DiffusionTrajectoryModel()
        self.trajectory_collector = TrajectoryCollector()
        self._use_ai_trajectory = False  # enabled when model loads successfully
        self._running = False
        self._vision_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_table_corners = None

        # Load persisted data
        self.physics_adapter.load()
        self.data_collector.load()
        self.correction_model.load()
        # Load diffusion model if available
        if self.trajectory_model.load():
            self._use_ai_trajectory = True
            print(f"[Model] Diffusion trajectory model loaded "
                  f"({self.trajectory_model.get_param_count():,} params)")
        else:
            print("[Model] No diffusion model found, using physics engine")

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start(self) -> None:
        print("[System] Starting Pool AR System...")
        system_state["match_mode"] = self.match_mode
        system_state["training_mode"] = self.training_mode
        system_state["table_detector"] = self.table_detector
        system_state["ball_detector"] = self.ball_detector
        system_state["camera"] = self.camera
        system_state["physics"] = self.physics

        # Load persisted calibration
        cal_data = load_calibration()
        system_state["calibration"] = {
            "active": False,
            "markers": cal_data.get("markers", []) if cal_data else [],
            "saved": cal_data is not None,
        }
        if cal_data:
            print(f"[Calibration] Loaded saved calibration ({len(cal_data['markers'])} markers)")
        system_state["announcer"] = self.announcer

        try:
            self.camera = RtspCamera(
                settings.CAMERA_RTSP_URL, settings.CAMERA_FPS)
            self.camera.start()
            print(f"[Camera] Connected to {settings.CAMERA_RTSP_URL}")
        except Exception as e:
            print(f"[Camera] Failed: {e}")
            print("[Camera] Running in offline mode (no camera)")

        self._running = True
        self._vision_thread = threading.Thread(
            target=self._vision_loop, daemon=True)
        self._vision_thread.start()
        system_state["main_system"] = self
        print(f"[System] Started ({self.data_collector.count()} prior shots loaded)")
        phy = self.physics_adapter.get_adjusted_params()
        print(f"[System] Physics params: cushion={phy.cushion_restitution:.3f}, "
              f"friction={phy.ball_friction:.4f}")

        # Auto-train correction model if enough data accumulated
        if self.correction_model.load() or self.data_collector.count() >= 50:
            if not self.correction_model.is_trained() and self.data_collector.count() >= 50:
                self._auto_train()

    def stop(self) -> None:
        self._running = False
        if self.trajectory_collector.is_collecting:
            self.trajectory_collector.stop()
        if self.camera:
            self.camera.stop()
        self.correction_model.save()
        self.data_collector.save()
        self.physics_adapter.save()
        print("[System] Stopped (data saved)")

    def _process_camera_frame(self, frame, detect_balls=False):
        """处理单帧：桌检测→透视→(可选)球检测→JPEG编码

        Returns:
            (jpeg_bytes_or_None, warped_or_None, balls_or_None)
        """
        import cv2
        try:
            found = self.table_detector.find_table(frame.data)
            if not found:
                return None, None, None
            region = self.table_detector.get_table_region()
            self._last_table_corners = region.corners
            warped = self.table_detector.warp(frame.data)

            balls = None
            if detect_balls:
                balls = self.ball_detector.detect(warped)
                # Update system state
                system_state["table_state"]["balls"] = [
                    {"x": b.x, "y": b.y, "color": b.color,
                     "is_solid": b.is_solid, "is_stripe": b.is_stripe,
                     "is_black": b.is_black, "is_cue": b.is_cue}
                    for b in balls
                ]

            _, buf = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return buf.tobytes(), warped, balls
        except Exception:
            return None, None, None

    def _handle_pocket_events(self, balls) -> None:
        """处理进袋事件 → 更新比赛/训练 + 播报 + 数据采集"""
        if not balls:
            return
        events = self.pocket_detector.update(balls)
        if not events:
            return

        # 收集所有进袋球（用于match mode批量处理）
        match_potted = []
        match_foul = False

        for ev in events:
            # 1. Broadcast to phone app (per-event)
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast_pocket_event({
                        "color": ev.color,
                        "is_stripe": ev.is_stripe,
                        "is_solid": ev.is_solid,
                        "is_black": ev.is_black,
                        "is_cue": ev.is_cue,
                        "pocket": list(ev.pocket_pos),
                    }), self._loop,
                )

            # 2. Announcer: generate speech text → broadcast to projector (TTS)
            text = self.announcer.pocket_announce(
                ev.color, ev.is_stripe, ev.is_cue, ev.is_black)
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast_announce(text), self._loop,
                )

            # 3. Training mode: auto-judge shot result (first target ball only)
            if system_state["current_mode"] in ("training", "challenge"):
                if (ev.is_solid or ev.is_stripe) and not hasattr(self, '_training_processed'):
                    drill = self.training_mode.session.get_current_drill()
                    cue_final = (0, 0)
                    for b in balls:
                        if hasattr(b, 'is_cue') and b.is_cue:
                            cue_final = (b.x, b.y)
                            break
                    result = self.training_mode.process_auto_result(
                        target_pocketed=True, drill=drill, cue_final=cue_final,
                    )
                    shot_data = {
                        "target_pocketed": True,
                        "cue_pocketed": ev.is_cue,
                        "consecutive_successes": self.training_mode.session.consecutive_successes,
                        "drill_passed": result.get("passed", False),
                        "feedback": self.announcer.shot_result(
                            result.get("success", False),
                            result.get("cue_in_zone", True),
                            self.training_mode.session.consecutive_successes,
                            result.get("passed", False),
                        ),
                    }
                    if self._loop:
                        asyncio.run_coroutine_threadsafe(
                            manager.broadcast_shot_result(shot_data), self._loop,
                        )
                        asyncio.run_coroutine_threadsafe(
                            manager.broadcast_announce(shot_data["feedback"]), self._loop,
                        )
                    self._training_processed = True

            # 4. AI training: auto-advance to next drill
            ai = system_state.get("ai_training", {})
            if ai.get("active") and not ev.is_cue:
                idx = ai.get("drill_index", 0) + 1
                total = ai.get("total_drills", 10)
                ai["drill_index"] = idx
                if idx >= total:
                    ai["active"] = False
                    print(f"[AI] Collected {total} shots, auto-training model...")
                    self._auto_train()
                    if self._loop:
                        asyncio.run_coroutine_threadsafe(
                            manager.broadcast_announce(
                                "AI数据采集完成，开始训练模型"), self._loop,
                        )
                elif self._loop:
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast_announce(
                            f"第{idx+1}/{total}题，请按投影摆球"), self._loop,
                    )

            # 5. Collect potted balls for match mode (processed once after loop)
            if system_state["current_mode"] == "match":
                if ev.is_solid or ev.is_stripe:
                    match_potted.append({
                        "color": ev.color, "is_solid": ev.is_solid,
                        "is_stripe": ev.is_stripe, "is_black": False, "is_cue": False,
                    })
                if ev.is_black:
                    match_potted.append({
                        "color": "black", "is_solid": False,
                        "is_stripe": False, "is_black": True, "is_cue": False,
                    })
                if ev.is_cue:
                    match_foul = True

        # 清除训练标记
        self._training_processed = False

        # 6. Match mode: 一次性处理所有进袋球
        if system_state["current_mode"] == "match" and match_potted:
            self.match_mode.process_shot(match_potted, match_foul)
            if self._loop:
                asyncio.run_coroutine_threadsafe(
                    manager.broadcast_score(), self._loop,
                )
            if self.match_mode.state.game_over:
                winner = self.match_mode.state.winner or 1
                v_text = self.announcer.victory(winner)
                if self._loop:
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast_announce(v_text), self._loop,
                    )

    def _render_ai_training(self) -> str:
        """渲染AI训练题到投影"""
        ai = system_state.get("ai_training", {})
        if not ai.get("active"):
            return self.renderer.render_to_base64()

        from game.training_data import get_level, get_all_levels
        levels = get_all_levels()
        total = ai.get("total_drills", 10)
        idx = ai.get("drill_index", 0)

        # Cycle through all drills from all levels
        all_drills = []
        for lv in levels:
            for d in lv.drills:
                all_drills.append(d)

        if idx >= len(all_drills):
            all_drills = all_drills[:total]
            if idx >= len(all_drills):
                return self.renderer.render_to_base64()

        drill = all_drills[idx % len(all_drills)]
        cue_pos = (drill.cue_pos[0], drill.cue_pos[1])
        target_pos = (drill.target_pos[0], drill.target_pos[1])
        pocket_pos = (drill.pocket_pos[0], drill.pocket_pos[1])

        overlay = ProjectionOverlay(
            cue_path=[cue_pos, target_pos],
            target_path=[target_pos, pocket_pos],
            pocket=pocket_pos,
            target_pos=target_pos,
            cue_pos=cue_pos,
            cue_final_pos=drill.cue_landing_zone[:2],
            label=f"AI训练 {idx+1}/{total} · {drill.description}",
        )
        return self.renderer.render_to_base64(overlay)

    def _compute_and_render_shot(self, warped, balls):
        """计算推荐路线并渲染投影画面"""
        if not balls:
            return self.renderer.render_to_base64()

        # Find cue ball and target balls
        cue_ball = None
        targets = []
        is_match = system_state["current_mode"] == "match"

        for b in balls:
            if b.is_cue:
                cue_ball = b
            elif is_match:
                # In match mode, only recommend current player's balls
                s = self.match_mode.state
                if s.current_player == 1:
                    if (s.player1_balls == "solids" and b.is_solid) or \
                       (s.player1_balls == "stripes" and b.is_stripe) or \
                       b.is_black:
                        targets.append(b)
                else:
                    if (s.player2_balls == "solids" and b.is_solid) or \
                       (s.player2_balls == "stripes" and b.is_stripe) or \
                       b.is_black:
                        targets.append(b)
            else:
                # Training mode: show all non-cue balls
                targets.append(b)

        if not cue_ball or not targets:
            return self.renderer.render_to_base64()

        # Try AI trajectory prediction first
        if self._use_ai_trajectory and self.trajectory_model.is_trained():
            try:
                import numpy as np
                # Build initial ball states
                initial_balls = np.zeros((16, 8), dtype=np.float32)
                for i, b in enumerate(balls[:16]):
                    initial_balls[i, 0] = float(b.x)
                    initial_balls[i, 1] = float(b.y)
                    initial_balls[i, 4] = 1.0 if b.is_cue else 0.0
                    initial_balls[i, 5] = 1.0 if b.is_black else 0.0
                    initial_balls[i, 6] = 1.0 if b.is_solid else 0.0
                    initial_balls[i, 7] = 1.0 if b.is_stripe else 0.0

                shot_params = np.array([0.5, 0.0, 0.0], dtype=np.float32)
                speed_val = system_state["table_state"].get("last_cue_speed", 0)
                if speed_val > 0:
                    shot_params[0] = min(1.0, speed_val / 5.0)

                # Physics path as condition
                physics_path = None
                if targets:
                    cue_vec = Vec2(cue_ball.x, cue_ball.y)
                    t = targets[0]
                    phys_result = self.physics.find_best_shot(cue_vec, Vec2(t.x, t.y))
                    if phys_result.success:
                        physics_path = np.zeros((2, 8, 2), dtype=np.float32)
                        for j, p in enumerate(phys_result.cue_path[:8]):
                            physics_path[0, j] = [p.x, p.y]
                        for j, p in enumerate(phys_result.target_path[:8]):
                            physics_path[1, j] = [p.x, p.y]

                # Predict
                trajectory = self.trajectory_model.predict(
                    np.zeros((600, 1200, 3), dtype=np.uint8),
                    initial_balls, shot_params, physics_path,
                    condition_physics=True,
                )

                # Extract paths
                target_idx = 0
                for i, b in enumerate(balls[:16]):
                    if not b.is_cue:
                        target_idx = i
                        break

                cue_path = [(float(trajectory[0, f, 0]), float(trajectory[0, f, 1]))
                            for f in range(300)
                            if trajectory[0, f, 0] != 0 or trajectory[0, f, 1] != 0]
                tgt_path = [(float(trajectory[target_idx, f, 0]),
                              float(trajectory[target_idx, f, 1]))
                             for f in range(300)
                             if trajectory[target_idx, f, 0] != 0 or
                             trajectory[target_idx, f, 1] != 0]

                if not cue_path:
                    cue_path = [(cue_ball.x, cue_ball.y)]
                if not tgt_path:
                    tgt_path = [(targets[0].x, targets[0].y)]

                cue_final = cue_path[-1] if cue_path else None
                t = targets[0]
                overlay = ProjectionOverlay(
                    cue_path=cue_path,
                    target_path=tgt_path,
                    pocket=(tgt_path[-1][0], tgt_path[-1][1]) if tgt_path else (0.5, 0.5),
                    target_pos=(t.x, t.y),
                    cue_pos=(cue_ball.x, cue_ball.y),
                    cue_final_pos=cue_final,
                    label=f"AI: {t.color}",
                )
                return self.renderer.render_to_base64(overlay)
            except Exception as e:
                import traceback
                traceback.print_exc()
                # Fall through to physics engine

        # Physics: find best shot for each target
        cue_vec = Vec2(cue_ball.x, cue_ball.y)
        best_overlay = None
        best_score = float("inf")

        for t in targets:
            t_vec = Vec2(t.x, t.y)
            result = self.physics.find_best_shot(cue_vec, t_vec)
            if result.success:
                cue_final = None
                if result.cue_final_pos:
                    cue_final = (result.cue_final_pos.x, result.cue_final_pos.y)

                # Append speed if available
                speed_val = system_state["table_state"].get("last_cue_speed", 0)
                label = f"目标: {t.color}"
                if speed_val > 0:
                    label += f" | 杆速: {speed_val:.1f} m/s"

                overlay = ProjectionOverlay(
                    cue_path=[(p.x, p.y) for p in result.cue_path],
                    target_path=[(p.x, p.y) for p in result.target_path],
                    pocket=(result.target_pocket.x, result.target_pocket.y),
                    target_pos=(t.x, t.y),
                    cue_pos=(cue_ball.x, cue_ball.y),
                    cue_final_pos=cue_final,
                    cue_technique=self._recommend_technique(result),
                    cue_power=int(result.cue_speed * 10),
                    label=label,
                )

                # Score: prefer shorter distance to pocket
                dist = ((t.x - result.target_pocket.x) ** 2 +
                        (t.y - result.target_pocket.y) ** 2) ** 0.5
                if dist < best_score:
                    best_score = dist
                    best_overlay = overlay

        return self.renderer.render_to_base64(best_overlay)

    @staticmethod
    def _recommend_technique(result) -> str:
        """根据物理引擎结果推荐杆法"""
        if not result.success or not result.cue_final_pos:
            return "中杆"
        # 粗略判断：母球朝目标方向继续前进=高杆，后退=低杆
        dx = result.cue_final_pos.x - result.cue_path[0].x
        dy = result.cue_final_pos.y - result.cue_path[0].y
        fdx = result.cue_path[-1].x - result.cue_path[0].x
        fdy = result.cue_path[-1].y - result.cue_path[0].y
        # 如果母球停点在击球方向延长线上 → 高杆
        dot = dx * fdx + dy * fdy
        power_norm = result.cue_speed / 0.5
        if dot > 0.01:
            return "高杆" if power_norm > 0.6 else "中高杆"
        elif dot < -0.01:
            return "低杆" if power_norm > 0.6 else "中低杆"
        return "中杆"

    def _auto_train(self) -> None:
        """自动训练修正模型（后台线程，不阻塞主循环）"""
        import threading as _t
        def _train():
            try:
                from learning.dataset import ShotDataset
                ds = ShotDataset()
                for rec in self.data_collector.get_all():
                    features = [
                        rec.cue_x, rec.cue_y,
                        rec.target_x, rec.target_y,
                        rec.pocket_x, rec.pocket_y,
                        rec.power / 100.0,
                        rec.spin_x, rec.spin_y,
                        self.physics_adapter.params.cushion_restitution,
                        self.physics_adapter.params.ball_friction,
                        0.035,  # default pocket radius
                    ]
                    ds.add(features, [rec.cue_dx, rec.cue_dy, 0, 0,
                                       rec.obs_cue_final_x - rec.cue_x,
                                       rec.obs_cue_final_y - rec.cue_y])
                result = self.correction_model.train(ds, epochs=50, verbose=False)
                if "error" not in result:
                    print(f"[AI] Correction model trained: {result}")
                else:
                    print(f"[AI] Training deferred: {result.get('error')}")
            except Exception as e:
                print(f"[AI] Training error: {e}")
        _t.Thread(target=_train, daemon=True).start()

    def _do_calibration(self) -> None:
        cal = system_state["calibration"]
        if not cal["active"]:
            return
        if not self.camera or not self.camera.is_running():
            return

        markers = [
            (0.1, 0.1), (0.5, 0.1), (0.9, 0.1),
            (0.1, 0.5), (0.5, 0.5), (0.9, 0.5),
            (0.1, 0.9), (0.5, 0.9), (0.9, 0.9),
        ]
        cal["markers"] = markers

        cal_b64 = self.renderer.render_calibration_to_base64(markers)
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast_projection(cal_b64), self._loop,
            )

        frame = self.camera.get_frame()
        if frame and frame.valid and self._last_table_corners is not None:
            cal["table_detected"] = True
            cal["status"] = "Calibration image projected. Check alignment."
            # Persist calibration result
            corners_list = [(float(p[0]), float(p[1]))
                            for p in self._last_table_corners]
            try:
                save_calibration(corners_list, [[0]], markers)
                cal["saved"] = True
                print("[Calibration] Saved to disk")
            except Exception as e:
                print(f"[Calibration] Save error: {e}")
        else:
            cal["table_detected"] = False
            cal["status"] = "Waiting for camera..."

    def _vision_loop(self) -> None:
        frame_counter = 0
        while self._running:
            has_projector = self._loop and manager.has_projector_clients()
            has_preview = self._loop and manager.has_camera_preview_clients()
            need_vision = has_projector or has_preview or \
                system_state["calibration"]["active"]

            if need_vision and self.camera and self.camera.is_running():
                frame = self.camera.get_frame()
                if frame and frame.valid:
                    system_state["table_state"]["detected"] = True

                    # Full processing every 3 frames, preview only in between
                    do_full = (frame_counter % 3 == 0)
                    jpeg_bytes, warped, balls = self._process_camera_frame(
                        frame, detect_balls=do_full)

                    # Camera preview (always)
                    if has_preview and jpeg_bytes:
                        b64 = base64.b64encode(jpeg_bytes).decode("utf-8")
                        asyncio.run_coroutine_threadsafe(
                            manager.broadcast_camera_preview(b64), self._loop,
                        )

                    # Ball detection pipeline (every 3 frames)
                    if do_full and balls is not None:
                        # Pocket detection
                        self._handle_pocket_events(balls)

                        # Speed detection
                        cue_speed = self.speed_detector.update_with_balls(balls)
                        if cue_speed is not None and cue_speed > 0:
                            system_state["table_state"]["last_cue_speed"] = cue_speed
                            # Record speed in data collector for last shot
                            print(f"[Speed] Cue speed: {cue_speed} m/s")

                        # Feed trajectory collector (silent background)
                        if self.trajectory_collector.is_collecting and balls is not None:
                            self.trajectory_collector.feed_frame(balls)

                        # Update system state
                        system_state["table_state"]["detected"] = True
                        system_state["table_state"]["ball_count"] = len(balls)

                        # Broadcast table state to phone clients (for top-down view)
                        if self._loop:
                            asyncio.run_coroutine_threadsafe(
                                manager.broadcast_table_state(), self._loop,
                            )

                    frame_counter += 1

            # Calibration mode
            if system_state["calibration"]["active"]:
                self._do_calibration()
                time.sleep(1.0)
                continue

            # Render projection
            if has_projector:
                try:
                    ai = system_state.get("ai_training", {})
                    if ai.get("active"):
                        image_b64 = self._render_ai_training()
                    else:
                        balls_list = system_state["table_state"].get("balls", [])
                        image_b64 = self._compute_and_render_shot(None, balls_list)
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast_projection(image_b64), self._loop,
                    )
                except Exception:
                    pass
                time.sleep(0.3)
            else:
                time.sleep(0.1)

    @staticmethod
    def _get_local_ip() -> str:
        try:
            s = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
            s.settimeout(1)
            s.connect(("8.8.8.8", 80))
            ip = s.getsockname()[0]
            s.close()
            return ip
        except Exception:
            return socket.gethostbyname(socket.gethostname())

    @staticmethod
    def start_discovery_service() -> None:
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", 8001))

        local_ip = PoolARSystem._get_local_ip()
        print(f"[Discovery] Service started on {local_ip}:8001")

        while True:
            try:
                data, addr = sock.recvfrom(256)
                if data.decode().startswith("POOL_AR_DISCOVER"):
                    response = f"POOL_AR_SERVER:{local_ip}"
                    sock.sendto(response.encode(), addr)
                    print(f"[Discovery] Responded to {addr} -> {local_ip}")
            except Exception:
                pass


def create_app(system: PoolARSystem) -> FastAPI:
    app = FastAPI(title="Pool AR System")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(scoreboard_router)

    return app


async def main() -> None:
    system = PoolARSystem()
    system.start()

    disc_thread = threading.Thread(
        target=PoolARSystem.start_discovery_service, daemon=True)
    disc_thread.start()

    system.set_loop(asyncio.get_running_loop())

    app = create_app(system)
    print(f"\n[Server] Starting API at http://0.0.0.0:{settings.API_PORT}")
    print("[Server] Scoreboard at http://<ip>:{}/scoreboard".format(
        settings.API_PORT))
    print("[Server] Phone app can now discover and connect\n")

    config = uvicorn.Config(app, host=settings.API_HOST,
                            port=settings.API_PORT)
    server = uvicorn.Server(config)
    await server.serve()


if __name__ == "__main__":
    asyncio.run(main())
