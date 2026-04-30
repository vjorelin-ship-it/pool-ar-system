import asyncio
import base64
import sys
import os
import socket
import threading
import time
from typing import Optional

os.environ.setdefault('ULTRALYTICS_QUIET', '1')

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from config import settings
from calibration_store import save_calibration, load_calibration
from api.routes import router, system_state, _system_state_lock
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
from learning.data_collector import DataCollector
from learning.physics_adapter import PhysicsAdapter
from learning.diffusion_model import DiffusionTrajectoryModel
from learning.trajectory_collector import TrajectoryCollector
MODEL_PATH = os.path.join(os.path.dirname(__file__), 'learning', 'balls.pt')


class PoolARSystem:
    def __init__(self):
        self.camera: Optional[RtspCamera] = None
        self.table_detector = TableDetector()
        self.ball_detector = BallDetector()
        self._ml_detector = None
        self._has_ml = False
        self.physics = PhysicsEngine()
        self.match_mode = MatchMode()
        self.training_mode = TrainingMode()
        self.renderer = ProjectorRenderer()
        self.pocket_detector = PocketDetector()
        self.speed_detector = SpeedDetector()
        self.announcer = Announcer()
        self.data_collector = DataCollector()
        self.physics_adapter = PhysicsAdapter()
        self.trajectory_model = DiffusionTrajectoryModel()
        self.trajectory_collector = TrajectoryCollector(
            save_dir=settings.TRAJECTORY_DATA_DIR)
        self._use_ai_trajectory = False
        self._running = False
        self._vision_thread: Optional[threading.Thread] = None
        self._loop: Optional[asyncio.AbstractEventLoop] = None
        self._last_table_corners = None
        self._training_processed = False

        # Load persisted learning data
        self.physics_adapter.load()
        self.data_collector.load()

        # Load diffusion model if available
        if self.trajectory_model.load():
            self._use_ai_trajectory = True
            print(f"[Model] Diffusion trajectory model loaded "
                  f"({self.trajectory_model.get_param_count():,} params)")
        else:
            print("[Model] No diffusion model found, using physics engine")

        # Load ML ball detector if available
        try:
            from vision.ball_detector_ml import BallDetectorML
            self._ml_detector = BallDetectorML()
            if self._ml_detector.load(MODEL_PATH):
                self._has_ml = True
                print(f"[AI] ML ball detector loaded")
            else:
                print(f"[AI] No trained model found, using traditional detection")
        except ImportError:
            print("[AI] ultralytics not installed, using traditional detection")

    def set_loop(self, loop: asyncio.AbstractEventLoop) -> None:
        self._loop = loop

    def start(self) -> None:
        print("[System] Starting Pool AR System...")
        system_state["match_mode"] = self.match_mode
        system_state["training_mode"] = self.training_mode
        system_state["table_detector"] = self.table_detector
        system_state["ball_detector"] = self.ball_detector
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

        if getattr(settings, 'CAMERA_SOURCE', 'rtsp') == "websocket":
            from camera.ws_camera import WebSocketCamera
            self.camera = WebSocketCamera()
            self.camera.start()
            system_state["ws_camera"] = self.camera
            system_state["camera"] = self.camera
            print("[Camera] WebSocket camera mode (waiting for Android box)")
        else:
            try:
                self.camera = RtspCamera(
                    settings.CAMERA_RTSP_URL, settings.CAMERA_FPS)
                self.camera.start()
                system_state["camera"] = self.camera
                print(f"[Camera] Connected to {settings.CAMERA_RTSP_URL}")
            except Exception as e:
                print(f"[Camera] Failed: {e}")
                print("[Camera] Running in offline mode (no camera)")

        self._running = True
        self._vision_thread = threading.Thread(
            target=self._vision_loop, daemon=True)
        self._vision_thread.start()
        print(f"[System] Started ({self.data_collector.count()} prior shots loaded)")

    def stop(self) -> None:
        self._running = False
        if self.camera:
            self.camera.stop()
        if hasattr(self, 'trajectory_collector') and self.trajectory_collector.is_collecting:
            self.trajectory_collector.stop()
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
                if self._has_ml and self._ml_detector is not None:
                    try:
                        balls = self._ml_detector.detect(warped)
                    except Exception:
                        import traceback
                        traceback.print_exc()
                        balls = None
                if not balls:
                    # Fall back to traditional detection
                    balls = self.ball_detector.detect(warped)
                # Update system state
                # Store both serialized dicts (for phone API) and raw objects (for renderer)
                with _system_state_lock:
                    system_state["table_state"]["balls"] = [
                        {"x": float(b.x), "y": float(b.y), "color": b.color,
                         "is_solid": bool(b.is_solid), "is_stripe": bool(b.is_stripe),
                         "is_black": bool(b.is_black), "is_cue": bool(b.is_cue)}
                        for b in balls
                    ]
                    system_state["table_state"]["ball_objects"] = balls

            _, buf = cv2.imencode(".jpg", warped, [cv2.IMWRITE_JPEG_QUALITY, 70])
            return buf.tobytes(), warped, balls
        except Exception:
            import traceback
            traceback.print_exc()
            return None, None, None

    def _handle_pocket_events(self, balls) -> None:
        """处理进袋事件 → 更新比赛/训练 + 播报 + 数据采集"""
        if not balls:
            return
        current_mode = system_state["current_mode"]  # snapshot once
        events = self.pocket_detector.update(balls)
        if not events:
            return

        # 收集所有进袋球（用于match mode批量处理）
        match_potted = []
        match_foul = False
        cue_pocketed = False

        for ev in events:
            # 0. Record to persisted history (for scoreboard refresh/reconnect)
            pocketed_entry = {
                "color": ev.color,
                "is_stripe": ev.is_stripe,
                "is_solid": ev.is_solid,
                "is_black": ev.is_black,
                "is_cue": ev.is_cue,
            }
            system_state["pocketed_balls"].append(pocketed_entry)

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

            # 3. Training mode: auto-judge shot result
            # NOTE: Currently marks target_pocketed=True for any solid/stripe pocketed.
            # TODO: Verify pocketed ball matches drill target by color/position.
            # The drill defines a target position; we should confirm the ball pocketed
            # at that position matches the expected target before marking success.
            if current_mode in ("training", "challenge"):
                if (ev.is_solid or ev.is_stripe) and not self._training_processed:
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
                    self.training_mode.save_history()

            # 4. AI training: auto-advance to next drill
            ai = system_state.get("ai_training", {})
            if ai.get("active") and not ev.is_cue:
                idx = ai.get("drill_index", 0) + 1
                total = ai.get("total_drills", 10)
                ai["drill_index"] = idx
                if idx >= total:
                    ai["active"] = False
                    print(f"[AI] Collected {total} shots, deactivating AI training")
                elif self._loop:
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast_announce(
                            f"第{idx+1}/{total}题，请按投影摆球"), self._loop,
                    )

            # 5. Collect potted balls and track fouls for match mode
            if current_mode == "match":
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
                    cue_pocketed = True

        # 清除训练标记
        self._training_processed = False

        # 6. Match mode: process shot with full foul detection
        if current_mode == "match" and (match_potted or match_foul):
            result = self.match_mode.process_shot(
                match_potted, is_foul=match_foul,
                cue_pocketed=match_foul,
            )
            self.match_mode.save_history()

            # Foul announcement
            if result.get("foul"):
                foul_text = self.announcer.foul_announce(
                    [{"desc": "犯规", "severity": "foul"}])
                if self._loop:
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast_announce(foul_text), self._loop)
            if result.get("free_ball"):
                fb_text = self.announcer.free_ball_announce()
                if self._loop:
                    asyncio.run_coroutine_threadsafe(
                        manager.broadcast_announce(fb_text), self._loop)

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

    # ── Ball ML training readiness ──

    @staticmethod
    def _ball_ml_count() -> int:
        """Count annotated ball detection images (images/ with labels/)."""
        import os as _os
        from config import settings
        img_dir = _os.path.join(settings.BALL_ML_DATA_DIR, "images")
        if not _os.path.isdir(img_dir):
            return 0
        return len([f for f in _os.listdir(img_dir) if f.endswith('.jpg')])

    @staticmethod
    def _is_ball_ml_ready() -> bool:
        """Ball detection ML is considered ready when >= 30 annotated images."""
        return PoolARSystem._ball_ml_count() >= 30

    @staticmethod
    def _annotate_preview(warped, balls):
        """Draw ball circles and numbers on the warped frame for preview."""
        import cv2
        h, w = warped.shape[:2]
        annotated = warped.copy()
        ball_names = {
            "white": "C", "black": "8",
            "solid_yellow": "1", "solid_blue": "2", "solid_red": "3",
            "solid_purple": "4", "solid_orange": "5", "solid_green": "6",
            "solid_brown": "7",
            "stripe_yellow": "9", "stripe_blue": "10", "stripe_red": "11",
            "stripe_purple": "12", "stripe_orange": "13", "stripe_green": "14",
            "stripe_brown": "15",
        }
        for b in balls:
            px, py = int(b.x * w), int(b.y * h)
            r = max(10, int(getattr(b, 'radius', 15)))
            name = ball_names.get(getattr(b, 'color', ''), '?')
            # Circle
            color = (0, 255, 255) if getattr(b, 'is_cue', False) else \
                    (0, 0, 0) if getattr(b, 'is_black', False) else \
                    (255, 200, 0) if getattr(b, 'is_solid', False) else \
                    (0, 200, 255)
            cv2.circle(annotated, (px, py), r, color, 2)
            # Number label
            cv2.putText(annotated, name, (px - r, py - r - 4),
                        cv2.FONT_HERSHEY_SIMPLEX, 0.6, color, 2)
        return annotated

    @staticmethod
    def _recommend_technique(result) -> str:
        """根据物理引擎结果推荐杆法"""
        if not result.success or not result.cue_final_pos:
            return "中杆"
        # Use explicit spin info when available
        if hasattr(result, 'spin_y') and result.spin_y != 0:
            sy = result.spin_y
            sx = abs(result.spin_x) if hasattr(result, 'spin_x') else 0
            if sy > 0.2:
                suf = "高杆" + ("加塞" if sx > 0.3 else "")
            elif sy < -0.2:
                suf = "低杆" + ("加塞" if sx > 0.3 else "")
            else:
                suf = "定杆" + ("加塞" if sx > 0.3 else "")
            return suf
        # Fallback to original heuristics
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

    # ── shot recommendation ──

    def _do_calibration(self) -> None:
        import cv2
        cal = system_state["calibration"]
        if not cal["active"]:
            return
        if not self.camera or not self.camera.is_running():
            cal["status"] = "Camera not available"
            return

        markers = [
            (0.1, 0.1), (0.5, 0.1), (0.9, 0.1),
            (0.1, 0.5), (0.5, 0.5), (0.9, 0.5),
            (0.1, 0.9), (0.5, 0.9), (0.9, 0.9),
        ]
        cal["markers"] = markers

        # Step 1: Project calibration pattern
        cal_b64 = self.renderer.render_calibration_to_base64(markers)
        if self._loop:
            asyncio.run_coroutine_threadsafe(
                manager.broadcast_projection(cal_b64), self._loop,
            )

        # Step 2: Wait briefly for projection to be visible, then capture
        time.sleep(0.3)
        frame = self.camera.get_frame()
        if not frame or not frame.valid:
            cal["status"] = "No camera frame"
            return

        # Step 3: Detect table and get warped overhead view
        found = self.table_detector.find_table(frame.data)
        if not found:
            cal["table_detected"] = False
            cal["status"] = "Table not detected"
            return

        region = self.table_detector.get_table_region()
        self._last_table_corners = region.corners
        warped = self.table_detector.warp(frame.data)
        cal["table_detected"] = True

        # Step 4: Detect projected markers in the warped overhead view
        detected = self._detect_calibration_markers(warped)
        if len(detected) < 4:
            cal["status"] = f"Detected only {len(detected)}/9 markers"
            return

        # Step 5: Match detected markers to known projector positions
        import numpy as _np
        # Sort both by spatial position (row-major: top-left to bottom-right)
        detected_sorted = sorted(detected, key=lambda p: (p[1], p[0]))
        markers_sorted = sorted(markers, key=lambda p: (p[1], p[0]))
        # The marker positions are in normalized projector coords [0,1]
        # We need them in the projector pixel space (1920x1080) for the homography
        proj_pixels = _np.array([
            [mx * self.renderer.WIDTH, my * self.renderer.HEIGHT]
            for mx, my in markers_sorted
        ], dtype=_np.float32)
        # Detected positions are in normalized camera coords [0,1] from warped view
        # Convert to the warped image pixel space for homography
        h_warped, w_warped = warped.shape[:2]
        cam_pixels = _np.array([
            [dx * w_warped, dy * h_warped]
            for dx, dy in detected_sorted
        ], dtype=_np.float32)

        # Step 6: Compute homography (camera → projector)
        H, mask = cv2.findHomography(cam_pixels, proj_pixels, cv2.RANSAC, 5.0)
        if H is None:
            cal["status"] = "Homography computation failed"
            return

        inliers = int(mask.sum()) if mask is not None else 0
        cal["homography_inliers"] = inliers
        cal["status"] = f"Calibrated ({inliers}/9 inliers)"

        # Step 7: Save
        corners_list = [(float(p[0]), float(p[1]))
                        for p in self._last_table_corners]
        try:
            save_calibration(corners_list, H.tolist(), markers)
            cal["saved"] = True
            print(f"[Calibration] Saved with homography ({inliers}/9 inliers)")
        except Exception as e:
            print(f"[Calibration] Save error: {e}")
            cal["status"] = "Save failed"

    @staticmethod
    def _detect_calibration_markers(warped):
        """Detect projected calibration markers in the warped overhead view.

        The markers are red crosshairs surrounded by green circles.
        Returns list of (x, y) normalized coordinates in [0,1].
        """
        import cv2
        import numpy as np
        h, w = warped.shape[:2]

        # Red channel minus grayscale to isolate red markers
        b, g, r = cv2.split(warped)
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        # Red prominence: R - max(G, B)
        red_map = r.astype(np.float32) - np.maximum(g, b).astype(np.float32)
        red_map = np.clip(red_map, 0, 255).astype(np.uint8)

        # Also try green prominence (green circles)
        green_map = g.astype(np.float32) - np.maximum(r, b).astype(np.float32)
        green_map = np.clip(green_map, 0, 255).astype(np.uint8)

        # Combine: markers are red + green
        combined = cv2.addWeighted(red_map, 0.6, green_map, 0.4, 0)

        # Threshold to find bright marker regions
        _, thresh = cv2.threshold(combined, 40, 255, cv2.THRESH_BINARY)
        # Morphological close to merge nearby pixels
        kernel = cv2.getStructuringElement(cv2.MORPH_ELLIPSE, (7, 7))
        closed = cv2.morphologyEx(thresh, cv2.MORPH_CLOSE, kernel)
        # Open to remove small noise
        opened = cv2.morphologyEx(closed, cv2.MORPH_OPEN, kernel)

        # Find contours → centroids
        contours, _ = cv2.findContours(opened, cv2.RETR_EXTERNAL, cv2.CHAIN_APPROX_SIMPLE)
        points = []
        for cnt in contours:
            area = cv2.contourArea(cnt)
            if area < 30 or area > 2000:
                continue
            M = cv2.moments(cnt)
            if M["m00"] < 1:
                continue
            cx = M["m10"] / M["m00"]
            cy = M["m01"] / M["m00"]
            points.append((float(cx / w), float(cy / h)))

        return points

    def _vision_loop(self) -> None:
        frame_counter = 0
        PROJECTION_FPS = 15      # target FPS for projection rendering
        IDLE_FPS = 10            # target FPS when idle
        proj_interval = 1.0 / PROJECTION_FPS
        idle_interval = 1.0 / IDLE_FPS
        last_proj_time = 0.0
        last_idle_time = 0.0

        while self._running:
            loop_start = time.time()
            has_projector = self._loop and manager.has_projector_clients()
            has_preview = self._loop and manager.has_camera_preview_clients()
            # Read calibration state under lock
            with _system_state_lock:
                cal_active = system_state["calibration"]["active"]
            need_vision = has_projector or has_preview or cal_active

            if need_vision and self.camera and self.camera.is_running():
                frame = self.camera.get_frame()
                if frame and frame.valid:
                    system_state["table_state"]["detected"] = True

                    # Full processing every 3 frames, preview only in between
                    do_full = (frame_counter % 3 == 0)
                    jpeg_bytes, warped, balls = self._process_camera_frame(
                        frame, detect_balls=do_full)

                    # Camera preview with ball annotations
                    if has_preview and jpeg_bytes:
                        if balls and self._is_ball_ml_ready():
                            # Draw ball numbers on warped frame
                            annotated = self._annotate_preview(warped, balls)
                            _, buf = cv2.imencode(".jpg", annotated,
                                                  [cv2.IMWRITE_JPEG_QUALITY, 75])
                            b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
                        else:
                            # Watermark: ball detection not trained
                            h, w = warped.shape[:2] if warped is not None else (800, 1600)
                            watermarked = warped.copy() if warped is not None else \
                                np.zeros((h, w, 3), dtype=np.uint8)
                            cv2.putText(watermarked, "Ball detection model not trained",
                                        (w // 8, h // 2), cv2.FONT_HERSHEY_SIMPLEX,
                                        1.2, (0, 0, 255), 2)
                            cv2.putText(watermarked, f"Annotated: {self._ball_ml_count()}/30 images",
                                        (w // 8, h // 2 + 40), cv2.FONT_HERSHEY_SIMPLEX,
                                        0.8, (200, 200, 200), 2)
                            _, buf = cv2.imencode(".jpg", watermarked,
                                                  [cv2.IMWRITE_JPEG_QUALITY, 75])
                            b64 = base64.b64encode(buf.tobytes()).decode("utf-8")
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
                            print(f"[Speed] Cue speed: {cue_speed} m/s")

                        # Update system state
                        system_state["table_state"]["detected"] = True
                        system_state["table_state"]["ball_count"] = len(balls)

                        # Broadcast table state to phone clients
                        if self._loop:
                            asyncio.run_coroutine_threadsafe(
                                manager.broadcast_table_state(), self._loop,
                            )

                    frame_counter += 1

            # Calibration mode
            if cal_active:
                self._do_calibration()
                time.sleep(1.0)
                continue

            # Render projection at target FPS
            if has_projector:
                elapsed = time.time() - last_proj_time
                if elapsed >= proj_interval:
                    try:
                        ai = system_state.get("ai_training", {})
                        if ai.get("active"):
                            image_b64 = self._render_ai_training()
                        else:
                            ball_objects = system_state["table_state"].get("ball_objects", [])
                            image_b64 = self._compute_and_render_shot(None, ball_objects)
                        asyncio.run_coroutine_threadsafe(
                            manager.broadcast_projection(image_b64), self._loop,
                        )
                        last_proj_time = time.time()
                        if frame_counter % 100 == 0:
                            print(f"[Projection] FPS: {PROJECTION_FPS} "
                                  f"(clients: {len(manager._projector_clients)})")
                    except Exception as e:
                        import traceback
                        traceback.print_exc()

                # Sleep to maintain target rate
                remain = proj_interval - (time.time() - loop_start)
                if remain > 0.001:
                    time.sleep(remain)
            else:
                elapsed = time.time() - last_idle_time
                if elapsed < idle_interval:
                    time.sleep(idle_interval - elapsed)
                last_idle_time = time.time()

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
            except Exception as e:
                print(f"[Discovery] Error: {e}")


def create_app(system: PoolARSystem) -> FastAPI:
    app = FastAPI(title="Pool AR System")

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=False,  # Per Fetch spec, cannot use * with credentials
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

    # Register shutdown handler
    import signal
    loop = asyncio.get_running_loop()
    def _shutdown():
        print("\n[System] Shutting down...")
        system.stop()
    try:
        for sig in (signal.SIGINT, signal.SIGTERM):
            loop.add_signal_handler(sig, _shutdown)
    except NotImplementedError:
        pass  # Windows doesn't support add_signal_handler

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
