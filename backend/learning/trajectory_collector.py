"""TrajectoryCollector -- silent background trajectory data recorder.

Records ball trajectories during live play by detecting cue-ball strikes
(trigger via relative-motion threshold) and saving shot recordings to disk
as JSON files for downstream training.
"""

from __future__ import annotations

import json
import math
import os
import threading
import time
from typing import Any, Dict, List, Optional, Tuple


class TrajectoryCollector:
    """Silent background recorder that captures shot trajectories.

    Operates in two layers:
      - *Ring buffer*: always-on, stores the most recent frames (incl. pre-trigger).
      - *Recording*: active only while a shot is in progress.

    Thread-safe: all state mutations are guarded by a ``threading.Lock()`` so
    ``feed_frame`` can be safely called from the vision thread.

    Parameters
    ----------
    save_dir : str
        Directory where shot JSON files are written.  Auto-created.
        Defaults to ``backend/learning/collected_shots/``.
    ring_size : int
        Number of pre-trigger frames kept in the ring buffer.
    stop_frames : int
        Consecutive stillness checks before recording is stopped.
    trigger_sigma : float
        Standard-deviation multiplier for trigger detection.
    """

    def __init__(
        self,
        save_dir: str = "",
        ring_size: int = 30,
        stop_frames: int = 10,
        trigger_sigma: float = 3.0,
    ):
        # Resolve save_dir — save to "new" subdirectory for untrained data
        if not save_dir:
            base = os.path.dirname(os.path.abspath(__file__))
            save_dir = os.path.join(base, "collected_shots")
        self._save_dir = os.path.join(save_dir, "new")
        os.makedirs(self._save_dir, exist_ok=True)

        self._ring_size = ring_size
        self._stop_frames = stop_frames
        self._trigger_sigma = trigger_sigma

        # ---- lock for thread-safety ----
        self._lock = threading.Lock()

        # ---- state ----
        self._collecting: bool = False
        self._recording: bool = False

        # Ring buffer: stores the last ring_size + 50 frames (extra for pre-trigger pull).
        # Each entry is a dict: {"balls": [...], "frame_idx": int, "timestamp": float}
        self._ring: List[Dict[str, Any]] = []
        self._ring_capacity: int = ring_size + 50
        self._frame_counter: int = 0

        # Recording buffer (only populated when _recording is True)
        self._record_frames: List[Dict[str, Any]] = []
        self._record_events: List[Dict[str, Any]] = []

        # Cue-ball history for trigger detection: list of (x, y)
        self._cue_history: List[Tuple[float, float]] = []
        self._cue_max: int = 30

        # Stillness / abort counters
        self._still_checks: int = 0
        self._cue_miss_count: int = 0  # consecutive frames without cue ball while recording

        # Event tracking (simple collision / pocket detection)
        self._prev_balls: Optional[List[Dict[str, Any]]] = None
        self._seen_balls: set = set()  # IDs of balls seen in the current recording

        # Shot counter -- recovered from existing files
        self._shot_id: int = self._recover_next_shot_id()

    # ─── public properties ─────────────────────────────────────────────

    @property
    def is_collecting(self) -> bool:
        return self._collecting

    @property
    def is_recording(self) -> bool:
        return self._recording

    # ─── control ───────────────────────────────────────────────────────

    def start(self) -> None:
        """Enable collection: clear buffers, reset state, begin listening."""
        with self._lock:
            self._collecting = True
            self._recording = False
            self._ring.clear()
            self._record_frames.clear()
            self._record_events.clear()
            self._cue_history.clear()
            self._still_checks = 0
            self._cue_miss_count = 0
            self._frame_counter = 0
            self._prev_balls = None
            self._seen_balls.clear()

    def stop(self) -> None:
        """Disable collection and save any in-progress recording."""
        with self._lock:
            self._collecting = False
            if self._recording:
                self._save_recording()
            self._recording = False

    def count(self) -> int:
        """Return total number of collected shots (files on disk)."""
        return self._shot_id

    # ─── data feed ─────────────────────────────────────────────────────

    def feed_frame(self, balls: List[Any]) -> None:
        """Feed a list of Ball objects for one frame.

        Called from the vision thread after each camera frame is processed.
        Ball objects must expose at minimum:
          - ``x``, ``y`` (normalised float coords)
          - ``is_cue``, ``is_solid``, ``is_stripe``, ``is_black`` (bool)
          - ``color`` (str)
        """
        if not self._collecting:
            return

        # Extract ball info into serialisable dicts
        ball_dicts = [_ball_to_dict(b) for b in balls]

        timestamp = time.time()
        frame_entry = {
            "balls": ball_dicts,
            "frame_idx": self._frame_counter,
            "timestamp": timestamp,
        }

        with self._lock:
            # 1. Push into ring buffer
            self._ring.append(frame_entry)
            if len(self._ring) > self._ring_capacity:
                self._ring.pop(0)

            self._frame_counter += 1

            # 2. If not recording, check trigger
            if not self._recording:
                self._check_trigger(frame_entry)
            else:
                # 3. If recording, append frame and check stop / abort
                self._record_frames.append(frame_entry)
                self._detect_events(frame_entry)
                self._check_abort(frame_entry)
                if self._recording:  # may have been set to False by _check_abort
                    self._check_stop()
                self._prev_balls = ball_dicts

    # ─── trigger detection ─────────────────────────────────────────────

    def _check_trigger(self, frame_entry: Dict[str, Any]) -> None:
        """Maintain cue history and fire trigger on significant displacement.

        Algorithm:
          1. Find the cue ball in the current frame.
          2. Maintain a sliding window of the last 30 cue-ball positions.
          3. Compute the std dev σ of the positions in the window.
          4. If the current-frame displacement from the previous frame
             exceeds trigger_sigma * σ AND σ > 0, trigger recording.
        """
        cue_ball = _find_cue_ball(frame_entry["balls"])
        if cue_ball is None:
            return

        cx, cy = float(cue_ball["x"]), float(cue_ball["y"])

        # Maintain cue history
        self._cue_history.append((cx, cy))
        if len(self._cue_history) > self._cue_max:
            self._cue_history.pop(0)

        if len(self._cue_history) < 2:
            return

        # Compute sigma of window
        xs = [p[0] for p in self._cue_history]
        ys = [p[1] for p in self._cue_history]
        sigma_x = _std(xs)
        sigma_y = _std(ys)
        sigma = math.sqrt(sigma_x ** 2 + sigma_y ** 2)

        if sigma <= 0.0:
            return

        # Current displacement from previous frame
        px, py = self._cue_history[-2]
        displacement = math.hypot(cx - px, cy - py)

        if displacement > self._trigger_sigma * sigma:
            self._trigger_recording()

    def _trigger_recording(self) -> None:
        """Start recording: copy pre-trigger frames from ring buffer."""
        self._recording = True

        # Pull pre-trigger frames from ring (up to ring_size entries)
        pre_trigger = self._ring[-min(len(self._ring), self._ring_size):]
        self._record_frames = list(pre_trigger)

        self._record_events.clear()
        self._still_checks = 0
        self._cue_miss_count = 0
        self._prev_balls = None
        self._seen_balls = set()

        # Seed seen balls from pre-trigger frames
        for frm in self._record_frames:
            for b in frm["balls"]:
                self._seen_balls.add(b.get("color", ""))

    # ─── stop detection ───────────────────────────────────────────────

    def _check_stop(self) -> None:
        """Check whether the shot has ended.

        Compares the last 5 recorded frames.  If the maximum displacement
        of any ball across those frames is < 0.002 for *stop_frames*
        consecutive checks, the recording is saved and stopped.
        """
        if len(self._record_frames) < 6:
            return  # need at least 6 frames to compare last 5

        last5 = self._record_frames[-5:]
        max_disp = 0.0

        for i in range(len(last5) - 1):
            balls_a = last5[i]["balls"]
            balls_b = last5[i + 1]["balls"]
            disp = _max_ball_displacement(balls_a, balls_b)
            if disp > max_disp:
                max_disp = disp

        if max_disp < 0.002:
            self._still_checks += 1
        else:
            self._still_checks = 0

        if self._still_checks >= self._stop_frames:
            self._save_recording()
            self._recording = False

    # ─── abort condition ───────────────────────────────────────────────

    def _check_abort(self, frame_entry: Dict[str, Any]) -> None:
        """Abort the recording if the cue ball is missing for too long."""
        cue_ball = _find_cue_ball(frame_entry["balls"])
        if cue_ball is None:
            self._cue_miss_count += 1
        else:
            self._cue_miss_count = 0

        if self._cue_miss_count >= 5:
            # Discard the recording
            self._record_frames.clear()
            self._record_events.clear()
            self._recording = False
            self._still_checks = 0
            self._cue_miss_count = 0
            self._prev_balls = None
            self._seen_balls.clear()

    # ─── event detection ───────────────────────────────────────────────

    def _detect_events(self, frame_entry: Dict[str, Any]) -> None:
        """Detect simple events: collision and pocket.

        Collision: two balls approach very close (distance < 0.03) compared
        to the previous frame.
        Pocket: a ball disappears from the frame (was present in the
        previous frame, not found now).
        """
        balls = frame_entry["balls"]
        frame_idx = frame_entry["frame_idx"]

        # ---- pocket detection (ball disappearance) ----
        if self._prev_balls is not None:
            prev_colors = {b.get("color") for b in self._prev_balls}
            curr_colors = {b.get("color") for b in balls}
            disappeared = prev_colors - curr_colors
            for color in disappeared:
                # Ignore the cue ball -- it may have been potted (scratch)
                # but we treat it as a pocket event regardless
                self._record_events.append({
                    "frame": frame_idx,
                    "type": "pocket",
                    "ball_color": color,
                })

        # ---- collision detection (balls very close) ----
        CUES = ["white"]
        for i in range(len(balls)):
            for j in range(i + 1, len(balls)):
                bi = balls[i]
                bj = balls[j]
                dist = math.hypot(
                    float(bi["x"]) - float(bj["x"]),
                    float(bi["y"]) - float(bj["y"]),
                )
                # Collisions involve the cue ball
                # Also detect that balls have drawn closer than before
                if dist < 0.03 and (
                    bi.get("color") in CUES or bj.get("color") in CUES
                ):
                    # Check previous frame to ensure this is a new collision
                    was_close_before = False
                    if self._prev_balls is not None:
                        prev_i = _find_ball_by_color(self._prev_balls, bi.get("color", ""))
                        prev_j = _find_ball_by_color(self._prev_balls, bj.get("color", ""))
                        if prev_i is not None and prev_j is not None:
                            prev_dist = math.hypot(
                                float(prev_i["x"]) - float(prev_j["x"]),
                                float(prev_i["y"]) - float(prev_j["y"]),
                            )
                            if prev_dist < 0.03:
                                was_close_before = True

                    if not was_close_before:
                        other = bj if bi.get("color") in CUES else bi
                        self._record_events.append({
                            "frame": frame_idx,
                            "type": "collision",
                            "ball_color": other.get("color", "unknown"),
                        })

    # ─── persistence ───────────────────────────────────────────────────

    def _save_recording(self) -> None:
        """Write the current recording to disk as a JSON file."""
        if not self._record_frames:
            return

        shot_id = self._shot_id
        self._shot_id += 1

        # Build frames array: list of per-frame ball lists
        frames = []
        for frm in self._record_frames:
            frames.append(frm["balls"])

        # Determine timestamp from the last frame (or now)
        timestamp = self._record_frames[-1].get("timestamp", time.time()) if self._record_frames else time.time()

        record = {
            "shot_id": shot_id,
            "timestamp": timestamp,
            "frames": frames,
            "events": self._record_events,
        }

        filename = f"shot_{shot_id:06d}.json"
        filepath = os.path.join(self._save_dir, filename)
        with open(filepath, "w", encoding="utf-8") as f:
            json.dump(record, f, ensure_ascii=False)

    def _recover_next_shot_id(self) -> int:
        """Scan save_dir for existing shot_NNNNNN.json files and return the next ID."""
        max_id = -1
        try:
            for name in os.listdir(self._save_dir):
                if name.startswith("shot_") and name.endswith(".json"):
                    try:
                        num = int(name[5:11])  # "shot_" = 5 chars + 6 digits
                        if num > max_id:
                            max_id = num
                    except ValueError:
                        continue
        except OSError:
            pass
        return max_id + 1


# ==========================================================================
# Module-level helpers
# ==========================================================================

def _find_cue_ball(balls: List[Dict[str, Any]]) -> Optional[Dict[str, Any]]:
    """Find the cue ball in a list of ball dicts."""
    for b in balls:
        if b.get("is_cue"):
            return b
    return None


def _find_ball_by_color(
    balls: List[Dict[str, Any]], color: str,
) -> Optional[Dict[str, Any]]:
    """Find a ball by its color string."""
    for b in balls:
        if b.get("color") == color:
            return b
    return None


def _ball_to_dict(ball: Any) -> Dict[str, Any]:
    """Extract serialisable dict from a Ball object.

    Handles both the vision Ball class and the pocket_detector BallState
    dataclass (both share the same field names).
    """
    return {
        "x": float(ball.x),
        "y": float(ball.y),
        "is_cue": bool(ball.is_cue),
        "is_solid": bool(ball.is_solid),
        "is_stripe": bool(ball.is_stripe),
        "is_black": bool(ball.is_black),
        "color": str(ball.color),
    }


def _std(values: List[float]) -> float:
    """Sample standard deviation of a list of floats."""
    n = len(values)
    if n < 2:
        return 0.0
    mean = sum(values) / n
    variance = sum((v - mean) ** 2 for v in values) / (n - 1)
    return math.sqrt(variance)


def _max_ball_displacement(
    balls_a: List[Dict[str, Any]], balls_b: List[Dict[str, Any]],
) -> float:
    """Maximum displacement of any ball between two frame dicts.

    Matches balls by colour.  Returns 0.0 if no colours match.
    """
    max_d = 0.0
    for ba in balls_a:
        color = ba.get("color", "")
        bb = _find_ball_by_color(balls_b, color)
        if bb is None:
            continue
        d = math.hypot(float(ba["x"]) - float(bb["x"]), float(ba["y"]) - float(bb["y"]))
        if d > max_d:
            max_d = d
    return max_d
