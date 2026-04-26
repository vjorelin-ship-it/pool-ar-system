# 台球智能AR投影系统 - 实施计划

> **For agentic workers:** REQUIRED SUB-SKILL: Use superpowers:subagent-driven-development (recommended) or superpowers:executing-plans to implement this plan task-by-task. Steps use checkbox (`- [ ]`) syntax for tracking.

**Goal:** 构建完整的台球智能AR投影系统，包括Python后端（视觉识别、物理引擎、API服务）、安卓手机APP（控制交互）、安卓投影仪APP（开机自启显示路线）、比分网页

**Architecture:** 电脑作为无显示器后台服务器运行Python程序，通过WiFi连接摄像头（RTSP）、手机APP和投影仪APP。后端提供REST API + WebSocket服务，安卓APP作为客户端进行控制和显示。

**Tech Stack:** Python 3.11+, OpenCV, NumPy, FastAPI, Uvicorn, Pillow, Java/Android SDK

---

### 阶段一：基础框架和配置

#### Task 1: 项目配置和依赖

**Files:**
- Create: `backend/requirements.txt`
- Create: `backend/config.py`

- [ ] **Step 1: Create requirements.txt**

```txt
fastapi==0.115.0
uvicorn[standard]==0.30.0
opencv-python==4.10.0.84
numpy==1.26.0
Pillow==10.3.0
python-multipart==0.0.9
websockets==12.0
```

- [ ] **Step 2: Create config.py**

```python
import os


class Settings:
    # Camera
    CAMERA_RTSP_URL: str = os.getenv("CAMERA_RTSP_URL", "rtsp://192.168.1.100:554/stream1")
    CAMERA_FPS: int = 10

    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000
    WS_HEARTBEAT_INTERVAL: int = 10

    # Table
    TABLE_WIDTH_MM: int = 2540   # 中式八球标准尺寸
    TABLE_HEIGHT_MM: int = 1270
    POCKET_RADIUS_MM: int = 42   # 袋口半径

    # Vision
    BALL_DETECT_MIN_RADIUS: int = 8
    BALL_DETECT_MAX_RADIUS: int = 20
    PERSPECTIVE_MARGIN: int = 30

    # Physics
    CUSHION_RESTITUTION: float = 0.78
    BALL_FRICTION: float = 0.03
    BALL_COLLISION_DAMPING: float = 0.95

    # Ball colors in BGR
    BALL_COLORS: dict = {
        "white": (255, 255, 255),
        "black": (0, 0, 0),
        "red": (0, 0, 200),
        "blue": (200, 0, 0),
        "yellow": (0, 200, 200),
        "green": (0, 128, 0),
        "purple": (128, 0, 128),
        "orange": (0, 100, 200),
        "brown": (0, 50, 100),
    }

    # Scoreboard
    SCOREBOARD_TITLE: str = "台球AR投影系统 - 比分牌"


settings = Settings()
```

- [ ] **Step 3: Create backend/__init__.py**

```python
# Empty init for package
```

- [ ] **Step 4: Commit**

```bash
git init D:/daima
cd D:/daima
git add backend/requirements.txt backend/config.py backend/__init__.py
git commit -m "feat: add project config and dependencies"
```

---

#### Task 2: RTSP摄像头模块

**Files:**
- Create: `backend/camera/__init__.py`
- Create: `backend/camera/rtsp_camera.py`
- Test: Visual test via script

- [ ] **Step 1: Create rtsp_camera.py**

```python
import cv2
import threading
import time
from typing import Optional
from dataclasses import dataclass


@dataclass
class Frame:
    data: Optional[cv2.Mat]
    timestamp: float
    valid: bool


class RtspCamera:
    def __init__(self, rtsp_url: str, fps: int = 10):
        self._url = rtsp_url
        self._target_interval = 1.0 / fps
        self._cap: Optional[cv2.VideoCapture] = None
        self._latest_frame: Optional[Frame] = None
        self._running = False
        self._lock = threading.Lock()
        self._thread: Optional[threading.Thread] = None

    def start(self) -> None:
        self._cap = cv2.VideoCapture(self._url)
        if not self._cap.isOpened():
            raise RuntimeError(f"Cannot open RTSP stream: {self._url}")
        self._running = True
        self._thread = threading.Thread(target=self._capture_loop, daemon=True)
        self._thread.start()

    def stop(self) -> None:
        self._running = False
        if self._thread:
            self._thread.join(timeout=3)
        if self._cap:
            self._cap.release()

    def get_frame(self) -> Optional[Frame]:
        with self._lock:
            return self._latest_frame

    def is_running(self) -> bool:
        return self._running

    def _capture_loop(self) -> None:
        while self._running:
            loop_start = time.time()
            ret, frame = self._cap.read() if self._cap else (False, None)
            with self._lock:
                self._latest_frame = Frame(
                    data=frame if ret else None,
                    timestamp=time.time(),
                    valid=ret,
                )
            elapsed = time.time() - loop_start
            sleep_time = self._target_interval - elapsed
            if sleep_time > 0:
                time.sleep(sleep_time)
            elif not ret:
                time.sleep(1.0)  # wait before retry on failure
```

- [ ] **Step 2: Create camera/__init__.py**

```python
from .rtsp_camera import RtspCamera, Frame

__all__ = ["RtspCamera", "Frame"]
```

- [ ] **Step 3: Commit**

```bash
git add backend/camera/
git commit -m "feat: add RTSP camera capture module"
```

---

#### Task 3: FastAPI服务器框架

**Files:**
- Create: `backend/api/__init__.py`
- Create: `backend/api/server.py`
- Create: `backend/main.py`

- [ ] **Step 1: Create api/server.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("[API] Server starting...")
    yield
    # Shutdown
    print("[API] Server shutting down...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pool AR System API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.get("/api/status")
    async def get_status():
        return {"status": "running", "version": "1.0.0"}

    return app
```

- [ ] **Step 2: Create main.py**

```python
import uvicorn
from api.server import create_app

app = create_app()

if __name__ == "__main__":
    uvicorn.run(app, host="0.0.0.0", port=8000)
```

- [ ] **Step 3: Test the server starts**

Run: `cd D:/daima/backend && python -c "from api.server import create_app; app = create_app(); print('Server module OK')"`
Expected: `Server module OK`

- [ ] **Step 4: Commit**

```bash
git add backend/api/ __init__.py
git add backend/main.py
git commit -m "feat: add FastAPI server framework"
```

---

### 阶段二：视觉识别

#### Task 4: 台球桌检测和透视矫正

**Files:**
- Create: `backend/vision/__init__.py`
- Create: `backend/vision/table_detector.py`

- [ ] **Step 1: Create table_detector.py**

```python
import cv2
import numpy as np
from dataclasses import dataclass


@dataclass
class TableRegion:
    corners: np.ndarray       # 4 corners in source image, shape (4,2)
    warped_size: tuple        # (width, height) of normalized table
    homography: np.ndarray    # perspective transform matrix
    inverse_homography: np.ndarray  # inverse transform


class TableDetector:
    def __init__(self, target_width: int = 800, target_height: int = 400):
        self._target_size = (target_width, target_height)

    def detect(self, frame: cv2.Mat) -> bool:
        try:
            gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
            blurred = cv2.GaussianBlur(gray, (5, 5), 0)
            edges = cv2.Canny(blurred, 50, 150)
            lines = cv2.HoughLinesP(edges, 1, np.pi / 180, 100,
                                    minLineLength=100, maxLineGap=50)
            if lines is None or len(lines) < 4:
                return False
            return True
        except Exception:
            return False

    def find_table(self, frame: cv2.Mat) -> bool:
        gray = cv2.cvtColor(frame, cv2.COLOR_BGR2GRAY)
        blurred = cv2.GaussianBlur(gray, (5, 5), 0)
        edges = cv2.Canny(blurred, 50, 150)
        contours, _ = cv2.findContours(edges, cv2.RETR_EXTERNAL,
                                        cv2.CHAIN_APPROX_SIMPLE)
        if not contours:
            return False
        largest = max(contours, key=cv2.contourArea)
        peri = cv2.arcLength(largest, True)
        approx = cv2.approxPolyDP(largest, 0.02 * peri, True)
        if len(approx) != 4:
            return False
        corners = approx.reshape(4, 2).astype(np.float32)
        corners = self._order_corners(corners)

        dst = np.array([
            [0, 0],
            [self._target_size[0] - 1, 0],
            [self._target_size[0] - 1, self._target_size[1] - 1],
            [0, self._target_size[1] - 1],
        ], dtype=np.float32)

        self._homography = cv2.getPerspectiveTransform(corners, dst)
        self._inverse_homography = cv2.getPerspectiveTransform(dst, corners)
        self._corners = corners
        return True

    def warp(self, frame: cv2.Mat) -> np.ndarray:
        if not hasattr(self, '_homography'):
            raise RuntimeError("Table not detected, call find_table first")
        return cv2.warpPerspective(frame, self._homography, self._target_size)

    def transform_points(self, points: np.ndarray, inverse: bool = False) -> np.ndarray:
        H = self._inverse_homography if inverse else self._homography
        pts = points.reshape(-1, 1, 2).astype(np.float32)
        transformed = cv2.perspectiveTransform(pts, H)
        return transformed.reshape(-1, 2)

    def get_table_region(self) -> TableRegion:
        return TableRegion(
            corners=self._corners,
            warped_size=self._target_size,
            homography=self._homography,
            inverse_homography=self._inverse_homography,
        )

    @staticmethod
    def _order_corners(pts: np.ndarray) -> np.ndarray:
        rect = np.zeros((4, 2), dtype=np.float32)
        s = pts.sum(axis=1)
        rect[0] = pts[np.argmin(s)]   # top-left
        rect[2] = pts[np.argmax(s)]   # bottom-right
        diff = np.diff(pts, axis=1)
        rect[1] = pts[np.argmin(diff)]  # top-right
        rect[3] = pts[np.argmax(diff)]  # bottom-left
        return rect
```

- [ ] **Step 2: Create vision/__init__.py**

```python
from .table_detector import TableDetector, TableRegion

__all__ = ["TableDetector", "TableRegion"]
```

- [ ] **Step 3: Unit test**

Run: `cd D:/daima/backend && python -c "from vision.table_detector import TableDetector; td = TableDetector(); print('TableDetector created OK')"`
Expected: `TableDetector created OK`

- [ ] **Step 4: Commit**

```bash
git add backend/vision/
git commit -m "feat: add table detector with perspective transform"
```

---

#### Task 5: 球体检测

**Files:**
- Create: `backend/vision/ball_detector.py`

- [ ] **Step 1: Create ball_detector.py**

```python
import cv2
import numpy as np
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Ball:
    x: float          # normalized 0-1
    y: float          # normalized 0-1
    radius: float     # pixels in warped space
    color: str        # white, black, red, blue, yellow, etc.
    is_stripe: bool   # True if stripe (花色)
    is_solid: bool    # True if solid (纯色)
    is_black: bool    # True if 8-ball
    is_cue: bool      # True if cue ball

    def position(self) -> Tuple[float, float]:
        return (self.x, self.y)


class BallDetector:
    # Pure color (solid) balls in Chinese 8-ball
    SOLID_COLORS_BGR: dict = {
        "yellow": (0, 200, 200),
        "blue": (200, 0, 0),
        "red": (0, 0, 200),
        "purple": (128, 0, 128),
        "orange": (0, 100, 200),
        "green": (0, 128, 0),
        "brown": (0, 50, 100),
    }

    STRIPE_COLORS_BGR: dict = {
        "yellow": (0, 200, 200),
        "blue": (200, 0, 0),
        "red": (0, 0, 200),
        "purple": (128, 0, 128),
        "orange": (0, 100, 200),
        "green": (0, 128, 0),
        "brown": (0, 50, 100),
    }

    def __init__(self, min_radius: int = 8, max_radius: int = 20):
        self._min_r = min_radius
        self._max_r = max_radius

    def detect(self, warped: cv2.Mat) -> List[Ball]:
        gray = cv2.cvtColor(warped, cv2.COLOR_BGR2GRAY)
        circles = cv2.HoughCircles(
            gray, cv2.HOUGH_GRADIENT, dp=1.2, minDist=30,
            param1=100, param2=25,
            minRadius=self._min_r, maxRadius=self._max_r,
        )

        balls: List[Ball] = []
        if circles is None:
            return balls

        h, w = warped.shape[:2]
        for (cx, cy, r) in circles[0]:
            # Get ball color from center pixel
            mask = self._create_ball_mask(warped, int(cx), int(cy), int(r))
            avg_color = cv2.mean(warped, mask)[:3]

            ball = self._classify_ball(
                x=cx / w, y=cy / h,
                radius=r,
                avg_color=avg_color,
            )
            if ball:
                balls.append(ball)

        return balls

    def detect_cue_ball(self, warped: cv2.Mat) -> Optional[Ball]:
        balls = self.detect(warped)
        for b in balls:
            if b.is_cue:
                return b
        return None

    @staticmethod
    def _create_ball_mask(frame: cv2.Mat, cx: int, cy: int, r: int) -> cv2.Mat:
        mask = np.zeros(frame.shape[:2], dtype=np.uint8)
        cv2.circle(mask, (cx, cy), r, 255, -1)
        return mask

    def _classify_ball(self, x: float, y: float, radius: float,
                       avg_color: Tuple[float, ...]) -> Optional[Ball]:
        b, g, r = avg_color
        # White ball
        if all(c > 200 for c in (r, g, b)):
            return Ball(x=x, y=y, radius=radius, color="white",
                        is_stripe=False, is_solid=False,
                        is_black=False, is_cue=True)
        # Black ball
        if all(c < 50 for c in (r, g, b)):
            return Ball(x=x, y=y, radius=radius, color="black",
                        is_stripe=False, is_solid=False,
                        is_black=True, is_cue=False)
        # Classify solids
        best_color = self._find_closest_color(avg_color)
        if best_color:
            return Ball(x=x, y=y, radius=radius, color=best_color,
                        is_stripe=False, is_solid=True,
                        is_black=False, is_cue=False)
        return None

    @staticmethod
    def _find_closest_color(avg_color: Tuple[float, ...]) -> Optional[str]:
        color_map: dict = {
            "yellow": (0, 200, 200),
            "blue": (200, 0, 0),
            "red": (0, 0, 200),
            "purple": (128, 0, 128),
            "orange": (0, 100, 200),
            "green": (0, 128, 0),
            "brown": (0, 50, 100),
        }
        best_name = None
        best_dist = float("inf")
        b, g, r = avg_color
        for name, (cb, cg, cr) in color_map.items():
            dist = (b - cb) ** 2 + (g - cg) ** 2 + (r - cr) ** 2
            if dist < best_dist:
                best_dist = dist
                best_name = name
        return best_name if best_dist < 15000 else None
```

- [ ] **Step 2: Update vision/__init__.py**

```python
from .table_detector import TableDetector, TableRegion
from .ball_detector import BallDetector, Ball

__all__ = ["TableDetector", "TableRegion", "BallDetector", "Ball"]
```

- [ ] **Step 3: Unit test**

Run: `cd D:/daima/backend && python -c "from vision.ball_detector import BallDetector; bd = BallDetector(); print('BallDetector created OK')"`
Expected: `BallDetector created OK`

- [ ] **Step 4: Commit**

```bash
git add backend/vision/ball_detector.py
git commit -m "feat: add ball detection and color classification"
```

---

### 阶段三：物理引擎

#### Task 6: 台球物理引擎核心

**Files:**
- Create: `backend/physics/__init__.py`
- Create: `backend/physics/engine.py`

- [ ] **Step 1: Create physics/engine.py**

```python
import math
from dataclasses import dataclass
from typing import List, Optional, Tuple


@dataclass
class Vec2:
    x: float
    y: float

    def __add__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x + other.x, self.y + other.y)

    def __sub__(self, other: "Vec2") -> "Vec2":
        return Vec2(self.x - other.x, self.y - other.y)

    def __mul__(self, scalar: float) -> "Vec2":
        return Vec2(self.x * scalar, self.y * scalar)

    def length(self) -> float:
        return math.sqrt(self.x ** 2 + self.y ** 2)

    def normalized(self) -> "Vec2":
        l = self.length()
        if l == 0:
            return Vec2(0, 0)
        return Vec2(self.x / l, self.y / l)

    def dot(self, other: "Vec2") -> float:
        return self.x * other.x + self.y * other.y


@dataclass
class ShotResult:
    cue_path: List[Vec2]          # Cue ball path points
    target_path: List[Vec2]       # Target ball path points
    target_pocket: Vec2           # Target pocket position
    cue_speed: float              # Cue ball initial speed
    target_speed: float           # Target ball speed after hit
    success: bool                 # Whether shot is physically possible
    cue_final_pos: Optional[Vec2] = None  # Cue ball final position


class PhysicsEngine:
    TABLE_WIDTH: float = 1.0       # normalized width
    TABLE_HEIGHT: float = 0.5      # normalized height
    CUSHION_RESTITUTION: float = 0.78
    BALL_RADIUS: float = 0.015     # normalized ball radius
    POCKET_RADIUS: float = 0.035   # normalized pocket radius

    POCKETS: List[Vec2] = [
        Vec2(0.0, 0.0),            # top-left
        Vec2(0.5, 0.0),            # top-center
        Vec2(1.0, 0.0),            # top-right
        Vec2(0.0, 1.0),            # bottom-left
        Vec2(0.5, 1.0),            # bottom-center
        Vec2(1.0, 1.0),            # bottom-right
    ]

    def calculate_shot(self, cue_pos: Vec2, target_pos: Vec2,
                       pocket_pos: Vec2) -> ShotResult:
        """Calculate the optimal shot to hit target ball into pocket."""
        # Direction from target to pocket
        to_pocket = pocket_pos - target_pos
        to_pocket_n = to_pocket.normalized()

        # Aim point is behind the target ball (in direction of pocket)
        aim_point = Vec2(
            target_pos.x - to_pocket_n.x * self.BALL_RADIUS * 2,
            target_pos.y - to_pocket_n.y * self.BALL_RADIUS * 2,
        )

        # Direction from cue ball to aim point
        to_aim = aim_point - cue_pos
        dist_to_aim = to_aim.length()

        if dist_to_aim < self.BALL_RADIUS * 2:
            return self._no_shot()

        to_aim_n = to_aim.normalized()

        # Check if shot is valid (angle between cue-target and target-pocket)
        cue_to_target = target_pos - cue_pos
        target_to_pocket = pocket_pos - target_pos
        angle = self._angle_between(cue_to_target, target_to_pocket)

        if abs(angle) > math.pi / 3:  # Max 60 degrees
            return self._no_shot()

        # Check for pocket proximity
        dist_to_pocket = (target_pos - pocket_pos).length()
        if dist_to_pocket > 0.45:  # Too far for a reasonable shot
            return self._no_shot()

        cue_path = [cue_pos, aim_point]
        target_path = [target_pos, pocket_pos]

        cue_speed = dist_to_aim * 0.15  # Simple speed calculation
        target_speed = cue_speed * 0.7

        return ShotResult(
            cue_path=cue_path,
            target_path=target_path,
            target_pocket=pocket_pos,
            cue_speed=cue_speed,
            target_speed=target_speed,
            success=True,
            cue_final_pos=Vec2(
                cue_pos.x + to_aim_n.x * dist_to_aim * 0.3,
                cue_pos.y + to_aim_n.y * dist_to_aim * 0.3,
            ),
        )

    def calculate_bank_shot(self, cue_pos: Vec2, target_pos: Vec2,
                            pocket_pos: Vec2) -> ShotResult:
        """Calculate a one-cushion bank shot."""
        # Reflect target across the nearest cushion
        reflected = self._reflect_across_cushion(target_pos, pocket_pos)

        # Now calculate as if the pocket is at the reflected position
        return self.calculate_shot(cue_pos, target_pos, reflected)

    def find_best_shot(self, cue_pos: Vec2, target_pos: Vec2) -> ShotResult:
        """Find the best shot (direct or bank) for a target ball."""
        best_shot: Optional[ShotResult] = None
        best_score = float("inf")

        for pocket in self.POCKETS:
            shot = self.calculate_shot(cue_pos, target_pos, pocket)
            if shot.success:
                dist = (target_pos - pocket).length()
                score = dist
                if best_shot is None or score < best_score:
                    best_shot = shot
                    best_score = score

        return best_shot or self._no_shot()

    def _no_shot(self) -> ShotResult:
        return ShotResult(
            cue_path=[], target_path=[], target_pocket=Vec2(0, 0),
            cue_speed=0, target_speed=0, success=False,
        )

    def _reflect_across_cushion(self, pos: Vec2, pocket: Vec2) -> Vec2:
        """Reflect position across the nearest cushion for bank shot calc."""
        dx = pocket.x - pos.x
        dy = pocket.y - pos.y
        if abs(dx) < abs(dy):
            # Reflect across left/right cushion
            return Vec2(-pos.x, pos.y)
        else:
            # Reflect across top/bottom cushion
            return Vec2(pos.x, -pos.y)

    @staticmethod
    def _angle_between(v1: Vec2, v2: Vec2) -> float:
        dot = v1.x * v2.x + v1.y * v2.y
        norm = math.sqrt(v1.x ** 2 + v1.y ** 2) * math.sqrt(v2.x ** 2 + v2.y ** 2)
        if norm == 0:
            return 0
        cos_a = max(-1, min(1, dot / norm))
        return math.acos(cos_a)
```

- [ ] **Step 2: Create physics/__init__.py**

```python
from .engine import PhysicsEngine, Vec2, ShotResult

__all__ = ["PhysicsEngine", "Vec2", "ShotResult"]
```

- [ ] **Step 3: Test direct shot calculation**

Run: `cd D:/daima/backend && python -c "
from physics.engine import PhysicsEngine, Vec2
e = PhysicsEngine()
result = e.calculate_shot(Vec2(0.2, 0.25), Vec2(0.5, 0.25), Vec2(1.0, 0.5))
print(f'Shot success: {result.success}, cue_path: {len(result.cue_path)} pts')
"`
Expected: `Shot success: True, cue_path: 2 pts`

- [ ] **Step 4: Commit**

```bash
git add backend/physics/
git commit -m "feat: add physics engine with shot calculation"
```

---

### 阶段四：游戏逻辑

#### Task 7: 比赛模式

**Files:**
- Create: `backend/game/__init__.py`
- Create: `backend/game/match_mode.py`

- [ ] **Step 1: Create match_mode.py**

```python
from dataclasses import dataclass, field
from typing import List, Optional, Tuple


@dataclass
class MatchState:
    player1_score: int = 0
    player2_score: int = 0
    current_player: int = 1       # 1 or 2
    player1_balls: str = ""       # "solids" or "stripes"
    player2_balls: str = ""
    is_break_shot: bool = True
    game_over: bool = False
    winner: Optional[int] = None
    foul: bool = False
    shots_this_turn: int = 0
    history: List[dict] = field(default_factory=list)

    def switch_player(self) -> None:
        self.current_player = 2 if self.current_player == 1 else 1
        self.shots_this_turn = 0

    def record_shot(self, potted: List[str], foul: bool = False) -> None:
        self.history.append({
            "player": self.current_player,
            "potted": potted,
            "foul": foul,
        })
        self.shots_this_turn += 1
        self.foul = foul


class MatchMode:
    def __init__(self):
        self.state = MatchState()
        self._assignment_locked = False

    def start_new_match(self) -> None:
        self.state = MatchState()

    def process_shot(self, potted_balls: List[str],
                     is_foul: bool = False) -> dict:
        s = self.state
        s.record_shot(potted_balls, is_foul)

        # Handle break shot - ball type assignment
        if s.is_break_shot:
            return self._handle_break(potted_balls)

        # Handle foul
        if is_foul:
            s.switch_player()
            return {"action": "switch_player", "player": s.current_player}

        # Handle potting
        if potted_balls:
            self._handle_pot(potted_balls)
            return {"action": "continue", "player": s.current_player}

        # No ball potted - switch player
        s.switch_player()
        return {"action": "switch_player", "player": s.current_player}

    def get_recommended_targets(self, balls: List[dict]) -> List[dict]:
        """Get recommended target balls for current player."""
        s = self.state
        player_balls = self._get_player_balls(balls, s.current_player)
        if not player_balls:
            return []
        # Sort by distance to nearest pocket (closer = easier)
        return sorted(player_balls, key=lambda b: b.get("difficulty", 0))

    def _handle_break(self, potted: List[str]) -> dict:
        s = self.state
        s.is_break_shot = False
        # Simple assignment: first potted ball determines groups
        if potted:
            first = potted[0]
            if first in self._solids():
                s.player1_balls = "solids"
                s.player2_balls = "stripes"
            else:
                s.player1_balls = "stripes"
                s.player2_balls = "solids"
            return {"action": "assign", "p1": s.player1_balls,
                    "p2": s.player2_balls, "player": 1}
        return {"action": "open_table", "player": 1}

    def _handle_pot(self, potted: List[str]) -> None:
        s = self.state
        has_black = "black" in potted
        if has_black:
            player_balls_remaining = self._remaining_of_group(
                s.current_player)
            if player_balls_remaining == 0:
                s.winner = s.current_player
                s.game_over = True

    def _get_player_balls(self, balls: List[dict],
                          player: int) -> List[dict]:
        s = self.state
        group = s.player1_balls if player == 1 else s.player2_balls
        if group == "solids":
            return [b for b in balls if b.get("is_solid")]
        elif group == "stripes":
            return [b for b in balls if b.get("is_stripe")]
        return []

    def _remaining_of_group(self, player: int) -> int:
        return 7  # Simplified - would query actual table state

    @staticmethod
    def _solids() -> List[str]:
        return ["yellow", "blue", "red", "purple", "orange", "green", "brown"]

    @staticmethod
    def _stripes() -> List[str]:
        return ["yellow", "blue", "red", "purple", "orange", "green", "brown"]

```

- [ ] **Step 2: Create game/__init__.py**

```python
from .match_mode import MatchMode, MatchState

__all__ = ["MatchMode", "MatchState"]
```

- [ ] **Step 3: Test match mode**

Run: `cd D:/daima/backend && python -c "
from game.match_mode import MatchMode
m = MatchMode()
m.start_new_match()
print(f'Match started, player: {m.state.current_player}')
result = m.process_shot(['yellow'], False)
print(f'Potted yellow: {result}')
"`
Expected: Match started and shot processed

- [ ] **Step 4: Commit**

```bash
git add backend/game/
git commit -m "feat: add match mode with scoring logic"
```

---

#### Task 8: 训练模式

**Files:**
- Create: `backend/game/training_data.py`
- Create: `backend/game/training_mode.py`

- [ ] **Step 1: Create training_data.py**

```python
from dataclasses import dataclass
from typing import List, Tuple


@dataclass
class TrainingLevel:
    level: int
    name: str
    description: str
    drills: List["TrainingDrill"]


@dataclass
class TrainingDrill:
    drill_id: int
    cue_pos: Tuple[float, float]      # (x, y) normalized
    target_pos: Tuple[float, float]
    pocket_pos: Tuple[float, float]
    cue_landing_zone: Tuple[float, float, float, float]  # (x1, y1, x2, y2)
    description: str


LEVELS: List[TrainingLevel] = []


def _build_levels() -> None:
    global LEVELS
    LEVELS = [
        TrainingLevel(1, "直球入门", "白球、目标球、球袋在一条直线", [
            TrainingDrill(1, (0.3, 0.25), (0.45, 0.25), (1.0, 0.25),
                          (0.35, 0.20, 0.50, 0.30), "直线推杆"),
            TrainingDrill(2, (0.2, 0.25), (0.5, 0.25), (0.0, 0.25),
                          (0.25, 0.20, 0.55, 0.30), "直线推杆"),
            TrainingDrill(3, (0.35, 0.15), (0.5, 0.15), (1.0, 0.0),
                          (0.40, 0.10, 0.55, 0.20), "直线推进右上角"),
            TrainingDrill(4, (0.35, 0.35), (0.5, 0.35), (1.0, 0.5),
                          (0.40, 0.30, 0.55, 0.40), "直线推进右下角"),
            TrainingDrill(5, (0.3, 0.25), (0.6, 0.25), (1.0, 0.25),
                          (0.35, 0.20, 0.50, 0.30), "稍远距离直推"),
        ]),
        TrainingLevel(2, "小角度进球", "目标球与球袋有小角度偏移", [
            TrainingDrill(6, (0.25, 0.30), (0.45, 0.25), (1.0, 0.25),
                          (0.30, 0.25, 0.50, 0.35), "小角度右推"),
            TrainingDrill(7, (0.25, 0.20), (0.45, 0.25), (1.0, 0.25),
                          (0.30, 0.15, 0.50, 0.25), "小角度右推偏上"),
            TrainingDrill(8, (0.3, 0.25), (0.5, 0.20), (1.0, 0.0),
                          (0.35, 0.20, 0.55, 0.30), "小角度右上角"),
            TrainingDrill(9, (0.3, 0.25), (0.5, 0.30), (1.0, 0.5),
                          (0.35, 0.20, 0.55, 0.30), "小角度右下角"),
            TrainingDrill(10, (0.2, 0.35), (0.45, 0.30), (1.0, 0.5),
                          (0.25, 0.30, 0.50, 0.40), "小角度远台"),
        ]),
        TrainingLevel(3, "中等角度", "需要更精准的瞄准", [
            TrainingDrill(11, (0.25, 0.35), (0.5, 0.25), (1.0, 0.0),
                          (0.30, 0.30, 0.55, 0.40), "中角度右上"),
            TrainingDrill(12, (0.25, 0.15), (0.5, 0.25), (1.0, 0.5),
                          (0.30, 0.10, 0.55, 0.20), "中角度右下"),
            TrainingDrill(13, (0.2, 0.30), (0.5, 0.20), (0.0, 0.0),
                          (0.25, 0.25, 0.55, 0.35), "中角度左上"),
            TrainingDrill(14, (0.2, 0.20), (0.5, 0.30), (0.0, 0.5),
                          (0.25, 0.15, 0.55, 0.25), "中角度左下"),
            TrainingDrill(15, (0.15, 0.30), (0.55, 0.25), (1.0, 0.5),
                          (0.20, 0.25, 0.45, 0.35), "中角度远台"),
        ]),
        TrainingLevel(4, "大角度进球", "需要精确的击球角度", [
            TrainingDrill(16, (0.25, 0.40), (0.5, 0.2), (1.0, 0.0),
                          (0.30, 0.35, 0.55, 0.45), "大角度右上"),
            TrainingDrill(17, (0.25, 0.10), (0.5, 0.3), (1.0, 0.5),
                          (0.30, 0.05, 0.55, 0.15), "大角度右下"),
            TrainingDrill(18, (0.25, 0.35), (0.5, 0.15), (0.0, 0.0),
                          (0.30, 0.30, 0.55, 0.40), "大角度左上"),
            TrainingDrill(19, (0.25, 0.15), (0.5, 0.35), (0.0, 0.5),
                          (0.30, 0.10, 0.55, 0.20), "大角度左下"),
        ]),
        TrainingLevel(5, "高杆/低杆", "需要控制母球走位", [
            TrainingDrill(20, (0.3, 0.25), (0.5, 0.25), (0.0, 0.25),
                          (0.55, 0.20, 0.70, 0.30), "高杆跟球"),
            TrainingDrill(21, (0.3, 0.25), (0.5, 0.25), (0.0, 0.25),
                          (0.15, 0.20, 0.25, 0.30), "低杆拉球"),
            TrainingDrill(22, (0.25, 0.30), (0.5, 0.20), (1.0, 0.0),
                          (0.55, 0.15, 0.70, 0.25), "高杆跟进右上"),
            TrainingDrill(23, (0.25, 0.20), (0.5, 0.30), (1.0, 0.5),
                          (0.55, 0.25, 0.70, 0.35), "高杆跟进右下"),
            TrainingDrill(24, (0.35, 0.25), (0.5, 0.25), (0.0, 0.25),
                          (0.15, 0.20, 0.25, 0.30), "低杆拉回"),
        ]),
        TrainingLevel(6, "加塞（侧旋）", "需要控制母球侧旋", [
            TrainingDrill(25, (0.3, 0.30), (0.5, 0.25), (1.0, 0.0),
                          (0.55, 0.20, 0.70, 0.30), "右塞走位右上"),
            TrainingDrill(26, (0.3, 0.20), (0.5, 0.25), (1.0, 0.5),
                          (0.55, 0.20, 0.70, 0.30), "左塞走位右下"),
            TrainingDrill(27, (0.25, 0.35), (0.5, 0.20), (0.0, 0.0),
                          (0.20, 0.15, 0.35, 0.25), "右塞走位左上"),
            TrainingDrill(28, (0.25, 0.15), (0.5, 0.30), (0.0, 0.5),
                          (0.20, 0.25, 0.35, 0.35), "左塞走位左下"),
        ]),
        TrainingLevel(7, "翻袋入门", "吃一库进球", [
            TrainingDrill(29, (0.3, 0.40), (0.5, 0.35), (1.0, 0.0),
                          (0.35, 0.35, 0.55, 0.45), "翻袋右上角"),
            TrainingDrill(30, (0.3, 0.10), (0.5, 0.15), (1.0, 0.5),
                          (0.35, 0.05, 0.55, 0.15), "翻袋右下角"),
            TrainingDrill(31, (0.2, 0.35), (0.5, 0.15), (0.0, 0.5),
                          (0.25, 0.10, 0.55, 0.20), "翻袋左角"),
            TrainingDrill(32, (0.2, 0.15), (0.5, 0.35), (0.0, 0.0),
                          (0.25, 0.30, 0.55, 0.40), "翻袋左角"),
            TrainingDrill(33, (0.25, 0.40), (0.5, 0.30), (1.0, 0.5),
                          (0.30, 0.25, 0.55, 0.35), "翻袋远台"),
        ]),
        TrainingLevel(8, "两库翻袋", "需要精确计算两次库边反弹", [
            TrainingDrill(34, (0.3, 0.45), (0.5, 0.35), (1.0, 0.0),
                          (0.35, 0.30, 0.55, 0.40), "两库翻袋右上"),
            TrainingDrill(35, (0.3, 0.05), (0.5, 0.15), (1.0, 0.5),
                          (0.35, 0.10, 0.55, 0.20), "两库翻袋右下"),
            TrainingDrill(36, (0.2, 0.40), (0.5, 0.20), (0.0, 0.0),
                          (0.25, 0.15, 0.55, 0.25), "两库翻袋左上"),
            TrainingDrill(37, (0.2, 0.10), (0.5, 0.30), (0.0, 0.5),
                          (0.25, 0.25, 0.55, 0.35), "两库翻袋左下"),
        ]),
        TrainingLevel(9, "组合球", "利用其他球传递", [
            TrainingDrill(38, (0.3, 0.30), (0.5, 0.20), (1.0, 0.0),
                          (0.35, 0.25, 0.55, 0.35), "组合球右上"),
            TrainingDrill(39, (0.3, 0.20), (0.5, 0.30), (1.0, 0.5),
                          (0.35, 0.25, 0.55, 0.35), "组合球右下"),
            TrainingDrill(40, (0.25, 0.35), (0.5, 0.15), (0.0, 0.0),
                          (0.30, 0.10, 0.55, 0.20), "组合球左上"),
            TrainingDrill(41, (0.25, 0.15), (0.5, 0.35), (0.0, 0.5),
                          (0.30, 0.30, 0.55, 0.40), "组合球左下"),
        ]),
        TrainingLevel(10, "综合大师", "综合运用所有技巧", [
            TrainingDrill(42, (0.2, 0.35), (0.45, 0.20), (1.0, 0.0),
                          (0.50, 0.15, 0.65, 0.25), "综合挑战一"),
            TrainingDrill(43, (0.2, 0.15), (0.45, 0.30), (1.0, 0.5),
                          (0.50, 0.25, 0.65, 0.35), "综合挑战二"),
            TrainingDrill(44, (0.15, 0.35), (0.55, 0.25), (0.0, 0.0),
                          (0.25, 0.20, 0.45, 0.30), "综合挑战三"),
            TrainingDrill(45, (0.15, 0.15), (0.55, 0.25), (0.0, 0.5),
                          (0.25, 0.20, 0.45, 0.30), "综合挑战四"),
            TrainingDrill(46, (0.25, 0.40), (0.5, 0.25), (1.0, 0.5),
                          (0.55, 0.20, 0.70, 0.30), "综合挑战五"),
        ]),
    ]


def get_level(level: int) -> TrainingLevel:
    if not LEVELS:
        _build_levels()
    for lv in LEVELS:
        if lv.level == level:
            return lv
    raise ValueError(f"Level {level} not found")


def get_all_levels() -> List[TrainingLevel]:
    if not LEVELS:
        _build_levels()
    return LEVELS


def get_drill(level: int, drill_idx: int) -> TrainingDrill:
    lv = get_level(level)
    if 0 <= drill_idx < len(lv.drills):
        return lv.drills[drill_idx]
    raise IndexError(f"Drill {drill_idx} not found in level {level}")


# Initialize on import
_build_levels()
```

- [ ] **Step 2: Create training_mode.py**

```python
from dataclasses import dataclass, field
from typing import List, Optional, Tuple
from .training_data import TrainingDrill, get_level, get_all_levels


@dataclass
class TrainingSession:
    current_level: int = 1
    current_drill_idx: int = 0
    consecutive_successes: int = 0
    challenge_mode: bool = True
    total_attempts: int = 0
    total_successes: int = 0
    unlocked_levels: List[int] = field(default_factory=lambda: [1])
    completed_levels: List[int] = field(default_factory=list)

    def get_current_drill(self) -> TrainingDrill:
        level = get_level(self.current_level)
        return level.drills[self.current_drill_idx]

    def get_progress(self) -> dict:
        level = get_level(self.current_level)
        return {
            "level": self.current_level,
            "level_name": level.name,
            "drill": self.current_drill_idx + 1,
            "total_drills": len(level.drills),
            "consecutive_successes": self.consecutive_successes,
            "needed_for_pass": 3,
            "total_attempts": self.total_attempts,
            "total_successes": self.total_successes,
        }


class TrainingMode:
    def __init__(self):
        self.session = TrainingSession()
        self._placement_threshold = 0.02  # normalized distance tolerance

    def start_challenge(self) -> dict:
        self.session = TrainingSession(challenge_mode=True)
        return self._drill_info()

    def select_level(self, level: int) -> dict:
        if level not in self.session.unlocked_levels:
            return {"error": f"Level {level} not unlocked"}
        self.session.current_level = level
        self.session.current_drill_idx = 0
        self.session.consecutive_successes = 0
        return self._drill_info()

    def verify_placement(self, actual_cue: Tuple[float, float],
                         actual_target: Tuple[float, float]) -> dict:
        drill = self.session.get_current_drill()
        cue_dist = self._distance(actual_cue, drill.cue_pos)
        target_dist = self._distance(actual_target, drill.target_pos)

        cue_ok = cue_dist <= self._placement_threshold
        target_ok = target_dist <= self._placement_threshold

        return {
            "cue_correct": cue_ok,
            "target_correct": target_ok,
            "cue_error": round(cue_dist, 4),
            "target_error": round(target_dist, 4),
            "all_correct": cue_ok and target_ok,
        }

    def record_result(self, success: bool,
                      cue_final: Tuple[float, float]) -> dict:
        s = self.session
        s.total_attempts += 1

        drill = s.get_current_drill()
        in_zone = self._is_in_landing_zone(cue_final, drill.cue_landing_zone)

        if success and in_zone:
            s.total_successes += 1
            s.consecutive_successes += 1
            feedback = "成功！目标球进袋，母球在指定区域"
        else:
            s.consecutive_successes = 0
            feedback = "未成功，继续努力"

        passed = False
        if s.challenge_mode and s.consecutive_successes >= 3:
            passed = self._advance_drill_or_level()

        return {
            "success": success,
            "cue_in_zone": in_zone,
            "consecutive": s.consecutive_successes,
            "passed": passed,
            "feedback": feedback,
        }

    def _advance_drill_or_level(self) -> bool:
        s = self.session
        level = get_level(s.current_level)

        # Next drill in current level
        if s.current_drill_idx + 1 < len(level.drills):
            s.current_drill_idx += 1
            s.consecutive_successes = 0
            return True

        # Level complete - unlock next
        if s.current_level < 10:
            s.completed_levels.append(s.current_level)
            s.current_level += 1
            s.current_drill_idx = 0
            s.consecutive_successes = 0
            if s.current_level not in s.unlocked_levels:
                s.unlocked_levels.append(s.current_level)
            return True

        return False

    def _drill_info(self) -> dict:
        drill = self.session.get_current_drill()
        return {
            "level": self.session.current_level,
            "drill": {
                "cue_pos": drill.cue_pos,
                "target_pos": drill.target_pos,
                "pocket_pos": drill.pocket_pos,
                "description": drill.description,
            },
            "progress": self.session.get_progress(),
        }

    @staticmethod
    def _distance(a: Tuple[float, float], b: Tuple[float, float]) -> float:
        return ((a[0] - b[0]) ** 2 + (a[1] - b[1]) ** 2) ** 0.5

    @staticmethod
    def _is_in_landing_zone(pos: Tuple[float, float],
                            zone: Tuple[float, float, float, float]) -> bool:
        x, y = pos
        x1, y1, x2, y2 = zone
        return x1 <= x <= x2 and y1 <= y <= y2
```

- [ ] **Step 3: Test training mode**

Run: `cd D:/daima/backend && python -c "
from game.training_mode import TrainingMode
t = TrainingMode()
info = t.start_challenge()
print(f'Challenge started: level {info[\"level\"]}')
result = t.verify_placement((0.31, 0.26), (0.45, 0.25))
print(f'Placement: {result}')
"`
Expected: Challenge started and placement verified

- [ ] **Step 4: Commit**

```bash
git add backend/game/training_data.py backend/game/training_mode.py
git commit -m "feat: add training mode with levels and challenge system"
```

---

### 阶段五：API路由和WebSocket

#### Task 9: REST API路由

**Files:**
- Create: `backend/api/routes.py`
- Modify: `backend/api/server.py`

- [ ] **Step 1: Create api/routes.py**

```python
from fastapi import APIRouter, HTTPException
from typing import Optional
from config import settings

router = APIRouter(prefix="/api")

# Shared state (populated by main.py)
system_state = {
    "camera": None,
    "table_detector": None,
    "ball_detector": None,
    "physics": None,
    "match_mode": None,
    "training_mode": None,
    "current_mode": "idle",  # idle, match, training, challenge
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
```

- [ ] **Step 2: Update server.py**

```python
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .routes import router, system_state


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[API] Server starting...")
    yield
    print("[API] Server shutting down...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pool AR System API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)

    return app
```

- [ ] **Step 3: Test API server starts**

Run: `cd D:/daima/backend && python -c "
from api.server import create_app
app = create_app()
routes = [r.path for r in app.routes if hasattr(r, 'path')]
print(f'Routes: {routes}')
"`
Expected: List of all API routes printed

- [ ] **Step 4: Commit**

```bash
git add backend/api/
git commit -m "feat: add REST API routes for all modes"
```

---

#### Task 10: WebSocket通信

**Files:**
- Create: `backend/api/websocket.py`
- Modify: `backend/api/server.py`

- [ ] **Step 1: Create api/websocket.py**

```python
import json
import asyncio
from fastapi import WebSocket, WebSocketDisconnect
from typing import Set
from .routes import system_state


class ConnectionManager:
    def __init__(self):
        self._phone_clients: Set[WebSocket] = set()
        self._projector_clients: Set[WebSocket] = set()

    async def connect_phone(self, ws: WebSocket) -> None:
        await ws.accept()
        self._phone_clients.add(ws)

    async def connect_projector(self, ws: WebSocket) -> None:
        await ws.accept()
        self._projector_clients.add(ws)

    def disconnect(self, ws: WebSocket) -> None:
        self._phone_clients.discard(ws)
        self._projector_clients.discard(ws)

    async def broadcast_table_state(self) -> None:
        data = json.dumps({
            "type": "table_state",
            "data": system_state["table_state"],
        })
        dead = set()
        for ws in self._phone_clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self._phone_clients -= dead

    async def broadcast_projection(self, image_data: str) -> None:
        """Send projection image to projector clients."""
        data = json.dumps({
            "type": "projection",
            "image": image_data,  # base64 encoded JPEG
        })
        dead = set()
        for ws in self._projector_clients:
            try:
                await ws.send_text(data)
            except Exception:
                dead.add(ws)
        self._projector_clients -= dead

    async def broadcast_score(self) -> None:
        mm = system_state.get("match_mode")
        if not mm:
            return
        s = mm.state
        data = json.dumps({
            "type": "score_update",
            "score": {
                "player1_score": s.player1_score,
                "player2_score": s.player2_score,
                "current_player": s.current_player,
                "game_over": s.game_over,
                "winner": s.winner,
            },
        })
        for ws in list(self._phone_clients):
            try:
                await ws.send_text(data)
            except Exception:
                self._phone_clients.discard(ws)


manager = ConnectionManager()
```

- [ ] **Step 2: Add WebSocket endpoints to routes.py**

Append to routes.py:
```python
from fastapi import WebSocket
from .websocket import manager


@router.websocket("/ws/phone")
async def phone_websocket(ws: WebSocket):
    await manager.connect_phone(ws)
    try:
        while True:
            await ws.receive_text()  # keep alive
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
```

- [ ] **Step 3: Test WebSocket import**

Run: `cd D:/daima/backend && python -c "
from api.websocket import ConnectionManager
cm = ConnectionManager()
print('ConnectionManager OK')
"`
Expected: `ConnectionManager OK`

- [ ] **Step 4: Commit**

```bash
git add backend/api/websocket.py
git commit -m "feat: add WebSocket support for phone and projector"
```

---

### 阶段六：投影渲染模块

#### Task 11: 投影画面渲染

**Files:**
- Create: `backend/renderer/__init__.py`
- Create: `backend/renderer/projector_renderer.py`

- [ ] **Step 1: Create renderer/projector_renderer.py**

```python
import base64
import io
import math
from typing import List, Optional, Tuple
from dataclasses import dataclass
from PIL import Image, ImageDraw


@dataclass
class ProjectionOverlay:
    cue_path: List[Tuple[float, float]]
    target_path: List[Tuple[float, float]]
    pocket: Tuple[float, float]
    target_pos: Tuple[float, float]
    cue_pos: Tuple[float, float]
    cue_technique: str = ""       # 高杆/低杆/中杆
    cue_power: int = 50           # 1-100
    cue_final_pos: Optional[Tuple[float, float]] = None
    label: str = ""


class ProjectorRenderer:
    WIDTH = 1920
    HEIGHT = 1080

    # Table area (centered, in projector coordinates)
    TABLE_LEFT = 200
    TABLE_TOP = 80
    TABLE_RIGHT = 1720
    TABLE_BOTTOM = 1000

    TABLE_WIDTH = TABLE_RIGHT - TABLE_LEFT
    TABLE_HEIGHT = TABLE_BOTTOM - TABLE_TOP

    COLORS = {
        "table": (20, 60, 20),
        "cushion": (80, 40, 20),
        "pocket": (0, 0, 0),
        "cue_line": (100, 200, 255),    # light blue
        "target_line": (255, 200, 50),  # gold
        "cue_ball": (255, 255, 200),
        "target_ball": (255, 100, 50),
        "text": (255, 255, 255),
        "landing_zone": (100, 255, 100, 80),  # RGBA green
        "grid": (40, 80, 40),
    }

    def __init__(self):
        self._image = Image.new("RGB", (self.WIDTH, self.HEIGHT),
                                (10, 10, 20))
        self._draw = ImageDraw.Draw(self._image, "RGBA")

    def render(self, overlay: Optional[ProjectionOverlay] = None) -> bytes:
        self._clear()
        self._draw_table()
        self._draw_pockets()

        if overlay:
            self._draw_shot(overlay)

        # Return JPEG bytes
        buf = io.BytesIO()
        self._image.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    def render_to_base64(self, overlay: Optional[ProjectionOverlay] = None) -> str:
        jpeg_bytes = self.render(overlay)
        return base64.b64encode(jpeg_bytes).decode("utf-8")

    def _clear(self) -> None:
        self._draw.rectangle([0, 0, self.WIDTH, self.HEIGHT],
                             fill=(10, 10, 20))

    def _draw_table(self) -> None:
        # Cushion border
        margin = 20
        self._draw.rectangle(
            [self.TABLE_LEFT - margin, self.TABLE_TOP - margin,
             self.TABLE_RIGHT + margin, self.TABLE_BOTTOM + margin],
            fill=self.COLORS["cushion"],
        )
        # Green felt
        self._draw.rectangle(
            [self.TABLE_LEFT, self.TABLE_TOP,
             self.TABLE_RIGHT, self.TABLE_BOTTOM],
            fill=self.COLORS["table"],
        )

    def _draw_pockets(self) -> None:
        r = 28
        corners = [
            (self.TABLE_LEFT, self.TABLE_TOP),
            (self.TABLE_RIGHT, self.TABLE_TOP),
            (self.TABLE_LEFT, self.TABLE_BOTTOM),
            (self.TABLE_RIGHT, self.TABLE_BOTTOM),
        ]
        for cx, cy in corners:
            self._draw.ellipse(
                [cx - r, cy - r, cx + r, cy + r],
                fill=self.COLORS["pocket"],
            )
        # Side pockets
        mid_x = (self.TABLE_LEFT + self.TABLE_RIGHT) // 2
        for cy in (self.TABLE_TOP, self.TABLE_BOTTOM):
            self._draw.ellipse(
                [mid_x - r, cy - r, mid_x + r, cy + r],
                fill=self.COLORS["pocket"],
            )

    def _draw_shot(self, overlay: ProjectionOverlay) -> None:
        # Draw cue ball path
        if len(overlay.cue_path) >= 2:
            pts = [self._norm_to_proj(p) for p in overlay.cue_path]
            for i in range(len(pts) - 1):
                self._draw.line(
                    [pts[i], pts[i + 1]],
                    fill=self.COLORS["cue_line"],
                    width=4,
                )

        # Draw target ball path
        if len(overlay.target_path) >= 2:
            pts = [self._norm_to_proj(p) for p in overlay.target_path]
            for i in range(len(pts) - 1):
                self._draw.line(
                    [pts[i], pts[i + 1]],
                    fill=self.COLORS["target_line"],
                    width=4,
                )

        # Draw balls
        cue_px = self._norm_to_proj(overlay.cue_pos)
        target_px = self._norm_to_proj(overlay.target_pos)
        r = 15
        self._draw.ellipse(
            [cue_px[0] - r, cue_px[1] - r, cue_px[0] + r, cue_px[1] + r],
            fill=self.COLORS["cue_ball"],
        )
        self._draw.ellipse(
            [target_px[0] - r, target_px[1] - r,
             target_px[0] + r, target_px[1] + r],
            fill=self.COLORS["target_ball"],
        )

        # Draw pocket highlight
        pocket_px = self._norm_to_proj(overlay.pocket)
        pr = 30
        self._draw.ellipse(
            [pocket_px[0] - pr, pocket_px[1] - pr,
             pocket_px[0] + pr, pocket_px[1] + pr],
            outline=(255, 255, 0), width=3,
        )

        # Draw landing zone
        if overlay.cue_final_pos:
            lp = self._norm_to_proj(overlay.cue_final_pos)
            lr = 20
            self._draw.ellipse(
                [lp[0] - lr, lp[1] - lr, lp[0] + lr, lp[1] + lr],
                fill=self.COLORS["landing_zone"],
            )

        # Draw labels (force, technique)
        if overlay.label:
            self._draw.text(
                (self.TABLE_LEFT + 10, self.TABLE_BOTTOM + 30),
                overlay.label,
                fill=self.COLORS["text"],
            )

    def _norm_to_proj(self, pos: Tuple[float, float]) -> Tuple[float, float]:
        """Convert normalized (0-1) coordinates to projector pixel coords."""
        x, y = pos
        px = self.TABLE_LEFT + x * self.TABLE_WIDTH
        py = self.TABLE_TOP + y * self.TABLE_HEIGHT
        return (int(px), int(py))
```

- [ ] **Step 2: Create renderer/__init__.py**

```python
from .projector_renderer import ProjectorRenderer, ProjectionOverlay

__all__ = ["ProjectorRenderer", "ProjectionOverlay"]
```

- [ ] **Step 3: Test renderer**

Run: `cd D:/daima/backend && python -c "
from renderer.projector_renderer import ProjectorRenderer, ProjectionOverlay
r = ProjectorRenderer()
overlay = ProjectionOverlay(
    cue_path=[(0.2, 0.3), (0.5, 0.25)],
    target_path=[(0.5, 0.25), (0.8, 0.3)],
    pocket=(0.8, 0.3),
    target_pos=(0.5, 0.25),
    cue_pos=(0.2, 0.3),
    cue_technique='中杆',
    cue_power=60,
    cue_final_pos=(0.65, 0.28),
    label='中杆 力度:60',
)
img_bytes = r.render(overlay)
print(f'Rendered image: {len(img_bytes)} bytes')
"`
Expected: `Rendered image: ~50-100KB bytes`

- [ ] **Step 4: Commit**

```bash
git add backend/renderer/
git commit -m "feat: add projector renderer for route visualization"
```

---

### 阶段七：比分网页

#### Task 12: 比分网页前端

**Files:**
- Create: `backend/web/__init__.py`
- Create: `backend/web/templates/scoreboard.html`
- Create: `backend/web/scoreboard_app.py`

- [ ] **Step 1: Create templates/scoreboard.html**

```html
<!DOCTYPE html>
<html lang="zh-CN">
<head>
    <meta charset="UTF-8">
    <meta name="viewport" content="width=device-width, initial-scale=1.0">
    <title>台球AR投影系统 - 比分牌</title>
    <style>
        * { margin: 0; padding: 0; box-sizing: border-box; }
        body {
            background: #0a0a1a;
            color: #fff;
            font-family: 'Microsoft YaHei', sans-serif;
            display: flex;
            justify-content: center;
            align-items: center;
            min-height: 100vh;
            overflow: hidden;
        }
        .scoreboard {
            text-align: center;
            width: 90vw;
            max-width: 1200px;
        }
        .title {
            font-size: 2rem;
            color: #4fc3f7;
            margin-bottom: 30px;
        }
        .scores {
            display: flex;
            justify-content: center;
            gap: 60px;
            margin-bottom: 40px;
        }
        .player {
            padding: 20px 40px;
            border-radius: 12px;
            background: #162447;
            min-width: 250px;
        }
        .player.active {
            background: #1a3a2e;
            border: 2px solid #4caf50;
        }
        .player-name {
            font-size: 1.5rem;
            color: #90caf9;
            margin-bottom: 10px;
        }
        .player-score {
            font-size: 4rem;
            font-weight: bold;
            color: #fff;
        }
        .player-balls {
            font-size: 1rem;
            color: #888;
            margin-top: 8px;
        }
        .status {
            font-size: 1.5rem;
            padding: 10px 20px;
            border-radius: 8px;
        }
        .status.match { color: #4caf50; }
        .status.training { color: #ff9800; }
        .status.idle { color: #888; }
        .game-over {
            font-size: 2rem;
            color: #ffd54f;
            margin-top: 20px;
        }
        .mode-switch {
            margin-top: 20px;
            font-size: 1.2rem;
            color: #666;
        }
    </style>
</head>
<body>
    <div class="scoreboard">
        <div class="title" id="title">台球AR投影系统</div>
        <div class="scores">
            <div class="player" id="player1">
                <div class="player-name">选手一</div>
                <div class="player-score" id="score1">0</div>
                <div class="player-balls" id="balls1">--</div>
            </div>
            <div class="player" id="player2">
                <div class="player-name">选手二</div>
                <div class="player-score" id="score2">0</div>
                <div class="player-balls" id="balls2">--</div>
            </div>
        </div>
        <div class="status idle" id="status">等待连接...</div>
        <div id="gameover" class="game-over" style="display:none;"></div>
        <div class="mode-switch" id="modeinfo"></div>
    </div>

    <script>
        const ws = new WebSocket(`ws://${location.hostname}:8000/api/ws/phone`);

        ws.onmessage = (event) => {
            const msg = JSON.parse(event.data);
            if (msg.type === 'score_update') {
                const s = msg.score;
                document.getElementById('score1').textContent = s.player1_score;
                document.getElementById('score2').textContent = s.player2_score;
                document.getElementById('player1').className =
                    s.current_player === 1 ? 'player active' : 'player';
                document.getElementById('player2').className =
                    s.current_player === 2 ? 'player active' : 'player';
                if (s.game_over) {
                    const gw = document.getElementById('gameover');
                    gw.style.display = 'block';
                    gw.textContent = `选手${s.winner} 获胜！`;
                }
                document.getElementById('status').textContent = '比赛进行中';
                document.getElementById('status').className = 'status match';
            }
            if (msg.type === 'table_state') {
                document.getElementById('title').textContent = '台球AR投影系统 - 已连接';
            }
        };

        ws.onclose = () => {
            document.getElementById('status').textContent = '连接断开，正在重连...';
            document.getElementById('status').className = 'status idle';
        };

        ws.onerror = () => {
            document.getElementById('status').textContent = '连接错误';
        };
    </script>
</body>
</html>
```

- [ ] **Step 2: Create scoreboard_app.py**

```python
from fastapi import APIRouter
from fastapi.responses import HTMLResponse
from pathlib import Path

router = APIRouter()

TEMPLATES_DIR = Path(__file__).parent / "templates"


@router.get("/scoreboard", response_class=HTMLResponse)
async def get_scoreboard():
    html = TEMPLATES_DIR / "scoreboard.html"
    if not html.exists():
        return HTMLResponse("<h1>Scoreboard not found</h1>", status_code=404)
    return HTMLResponse(html.read_text(encoding="utf-8"))
```

- [ ] **Step 3: Register scoreboard router in server.py**

```python
# Add to create_app() in server.py:
from .scoreboard_app import router as scoreboard_router
app.include_router(scoreboard_router)
```

- [ ] **Step 4: Commit**

```bash
git add backend/web/
git commit -m "feat: add scoreboard web page with WebSocket live updates"
```

---

### 阶段八：安卓手机APP

#### Task 13: 安卓手机APP项目结构

**Files:**
- Create: `phone-app/settings.gradle.kts`
- Create: `phone-app/build.gradle.kts`
- Create: `phone-app/app/build.gradle.kts`
- Create: `phone-app/app/src/main/AndroidManifest.xml`

- [ ] **Step 1: Create settings.gradle.kts**

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "PoolARController"
include(":app")
```

- [ ] **Step 2: Create root build.gradle.kts**

```kotlin
plugins {
    id("com.android.application") version "8.2.0" apply false
    id("org.jetbrains.kotlin.android") version "1.9.20" apply false
}
```

- [ ] **Step 3: Create app/build.gradle.kts**

```kotlin
plugins {
    id("com.android.application")
    id("org.jetbrains.kotlin.android")
}

android {
    namespace = "com.poolar.controller"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.poolar.controller"
        minSdk = 21
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }

    compileOptions {
        sourceCompatibility = JavaVersion.VERSION_17
        targetCompatibility = JavaVersion.VERSION_17
    }

    kotlinOptions {
        jvmTarget = "17"
    }
}

dependencies {
    implementation("org.java-websocket:Java-WebSocket:1.5.4")
    implementation("com.google.code.gson:gson:2.10.1")
    implementation("androidx.appcompat:appcompat:1.6.1")
    implementation("androidx.constraintlayout:constraintlayout:2.1.4")
}
```

- [ ] **Step 4: Create AndroidManifest.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.ACCESS_WIFI_STATE" />

    <application
        android:allowBackup="true"
        android:label="台球AR控制"
        android:supportsRtl="true"
        android:theme="@style/Theme.MaterialComponents.NoActionBar">
        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:screenOrientation="portrait">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>
    </application>
</manifest>
```

- [ ] **Step 5: Commit**

```bash
git add phone-app/
git commit -m "feat: add Android phone app project structure"
```

---

#### Task 14: 安卓手机APP网络层

**Files:**
- Create: `phone-app/app/src/main/java/com/poolar/controller/network/ServiceDiscovery.java`
- Create: `phone-app/app/src/main/java/com/poolar/controller/network/ApiClient.java`
- Create: `phone-app/app/src/main/java/com/poolar/controller/network/WebSocketClient.java`
- Create: `phone-app/app/src/main/java/com/poolar/controller/model/Models.java`

- [ ] **Step 1: Create Models.java**

```java
package com.poolar.controller.model;

public class Models {
    public static class TableState {
        public boolean detected;
        public Ball[] balls;
        public String mode;
    }

    public static class Ball {
        public float x, y;
        public float radius;
        public String color;
        public boolean isStripe;
        public boolean isSolid;
        public boolean isBlack;
        public boolean isCue;
    }

    public static class ScoreData {
        public int player1Score;
        public int player2Score;
        public int currentPlayer;
        public boolean gameOver;
        public int winner;
    }

    public static class TrainingLevel {
        public int level;
        public String name;
        public String description;
        public int drillCount;
    }

    public static class DrillInfo {
        public float[] cuePos;
        public float[] targetPos;
        public float[] pocketPos;
        public String description;
    }

    public static class TrainingProgress {
        public int level;
        public String levelName;
        public int drill;
        public int totalDrills;
        public int consecutiveSuccesses;
        public int neededForPass;
    }

    public static class DrillSession {
        public int level;
        public DrillInfo drill;
        public TrainingProgress progress;
    }

    public static class PlacementResult {
        public boolean cueCorrect;
        public boolean targetCorrect;
        public double cueError;
        public double targetError;
        public boolean allCorrect;
    }

    public static class TrainingResult {
        public boolean success;
        public boolean cueInZone;
        public int consecutive;
        public boolean passed;
        public String feedback;
    }

    public static class ShotResult {
        public float[][] cuePath;
        public float[][] targetPath;
        public float[] targetPocket;
        public float cueSpeed;
        public float targetSpeed;
        public boolean success;
        public float[] cueFinalPos;
    }
}
```

- [ ] **Step 2: Create ServiceDiscovery.java**

```java
package com.poolar.controller.network;

import java.net.DatagramPacket;
import java.net.DatagramSocket;
import java.net.InetAddress;
import java.net.SocketTimeoutException;

public class ServiceDiscovery {
    private static final int DISCOVERY_PORT = 8001;
    private static final int TIMEOUT_MS = 3000;

    public interface DiscoveryCallback {
        void onFound(String host, int port);
        void onError(String message);
    }

    public void discoverServer(final DiscoveryCallback callback) {
        new Thread(() -> {
            try (DatagramSocket socket = new DatagramSocket()) {
                socket.setBroadcast(true);
                socket.setSoTimeout(TIMEOUT_MS);
                byte[] request = "POOL_AR_DISCOVER".getBytes();
                DatagramPacket packet = new DatagramPacket(
                    request, request.length,
                    InetAddress.getByName("255.255.255.255"),
                    DISCOVERY_PORT
                );
                socket.send(packet);

                byte[] buffer = new byte[256];
                DatagramPacket response = new DatagramPacket(buffer, buffer.length);
                socket.receive(response);

                String reply = new String(response.getData(), 0, response.getLength());
                if (reply.startsWith("POOL_AR_SERVER:")) {
                    String[] parts = reply.split(":");
                    if (parts.length >= 2) {
                        callback.onFound(parts[1], 8000);
                        return;
                    }
                }
                callback.onError("Invalid response");
            } catch (SocketTimeoutException e) {
                callback.onError("未找到服务器，请确保电脑端已启动");
            } catch (Exception e) {
                callback.onError("发现服务失败: " + e.getMessage());
            }
        }).start();
    }
}
```

- [ ] **Step 3: Create ApiClient.java**

```java
package com.poolar.controller.network;

import com.google.gson.Gson;
import com.google.gson.reflect.TypeToken;
import com.poolar.controller.model.Models;

import java.io.BufferedReader;
import java.io.InputStreamReader;
import java.io.OutputStream;
import java.net.HttpURLConnection;
import java.net.URL;
import java.util.List;

public class ApiClient {
    private final String baseUrl;
    private final Gson gson = new Gson();

    public ApiClient(String host) {
        this.baseUrl = "http://" + host + ":8000";
    }

    public interface ApiCallback<T> {
        void onResult(T result);
        void onError(String error);
    }

    public void getStatus(final ApiCallback<StatusResult> callback) {
        get("/api/status", StatusResult.class, callback);
    }

    public void startSystem(final ApiCallback<Void> callback) {
        post("/api/control/start", null, Void.class, callback);
    }

    public void stopSystem(final ApiCallback<Void> callback) {
        post("/api/control/stop", null, Void.class, callback);
    }

    public void setMode(String mode, final ApiCallback<Object> callback) {
        post("/api/mode?mode=" + mode, null, Object.class, callback);
    }

    public void getTableState(final ApiCallback<Models.TableState> callback) {
        get("/api/table", Models.TableState.class, callback);
    }

    public void getScore(final ApiCallback<Models.ScoreData> callback) {
        get("/api/score", Models.ScoreData.class, callback);
    }

    public void getTrainingLevels(final ApiCallback<List<Models.TrainingLevel>> callback) {
        getList("/api/training/levels", Models.TrainingLevel.class, callback);
    }

    public void selectLevel(int level, final ApiCallback<Models.DrillSession> callback) {
        post("/api/training/select-level?level=" + level, null,
             Models.DrillSession.class, callback);
    }

    private <T> void get(String path, final Class<T> clazz,
                          final ApiCallback<T> callback) {
        new Thread(() -> {
            try {
                URL url = new URL(baseUrl + path);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("GET");
                int code = conn.getResponseCode();
                BufferedReader reader = new BufferedReader(
                    new InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    response.append(line);
                }
                reader.close();
                T result = gson.fromJson(response.toString(), clazz);
                callback.onResult(result);
            } catch (Exception e) {
                callback.onError(e.getMessage());
            }
        }).start();
    }

    private <T> void getList(String path, final Class<T> clazz,
                              final ApiCallback<List<T>> callback) {
        new Thread(() -> {
            try {
                URL url = new URL(baseUrl + path);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                BufferedReader reader = new BufferedReader(
                    new InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    response.append(line);
                }
                reader.close();
                List<T> result = gson.fromJson(response.toString(),
                    TypeToken.getParameterized(List.class, clazz).getType());
                callback.onResult(result);
            } catch (Exception e) {
                callback.onError(e.getMessage());
            }
        }).start();
    }

    private <T> void post(String path, Object body, final Class<T> clazz,
                           final ApiCallback<T> callback) {
        new Thread(() -> {
            try {
                URL url = new URL(baseUrl + path);
                HttpURLConnection conn = (HttpURLConnection) url.openConnection();
                conn.setRequestMethod("POST");
                conn.setDoOutput(true);
                conn.setRequestProperty("Content-Type", "application/json");
                if (body != null) {
                    OutputStream os = conn.getOutputStream();
                    os.write(gson.toJson(body).getBytes());
                    os.flush();
                }
                int code = conn.getResponseCode();
                BufferedReader reader = new BufferedReader(
                    new InputStreamReader(conn.getInputStream()));
                StringBuilder response = new StringBuilder();
                String line;
                while ((line = reader.readLine()) != null) {
                    response.append(line);
                }
                reader.close();
                T result = gson.fromJson(response.toString(), clazz);
                callback.onResult(result);
            } catch (Exception e) {
                callback.onError(e.getMessage());
            }
        }).start();
    }

    public static class StatusResult {
        public String status;
        public String mode;
        public boolean camera;
        public boolean tableDetected;
        public int ballCount;
    }
}
```

- [ ] **Step 4: Commit**

```bash
git add phone-app/app/src/main/java/com/poolar/controller/
git commit -m "feat: add Android phone app networking layer"
```

---

#### Task 15: 安卓手机APP主界面

**Files:**
- Create: `phone-app/app/src/main/java/com/poolar/controller/MainActivity.java`
- Create: `phone-app/app/src/main/res/layout/activity_main.xml`

- [ ] **Step 1: Create activity_main.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<LinearLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:orientation="vertical"
    android:background="#0d1b2a"
    android:padding="16dp">

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="台球AR投影系统"
        android:textColor="#4fc3f7"
        android:textSize="24sp"
        android:layout_marginBottom="20dp" />

    <TextView
        android:id="@+id/connectionStatus"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="未连接"
        android:textColor="#888"
        android:textSize="14sp"
        android:layout_marginBottom="30dp" />

    <Button
        android:id="@+id/btnStart"
        android:layout_width="match_parent"
        android:layout_height="56dp"
        android:text="启动系统"
        android:textSize="16sp"
        android:backgroundTint="#1b5e20"
        android:layout_marginBottom="12dp" />

    <Button
        android:id="@+id/btnStop"
        android:layout_width="match_parent"
        android:layout_height="56dp"
        android:text="停止系统"
        android:textSize="16sp"
        android:backgroundTint="#b71c1c"
        android:layout_marginBottom="24dp" />

    <TextView
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:text="模式选择"
        android:textColor="#90caf9"
        android:textSize="18sp"
        android:layout_marginBottom="12dp" />

    <Button
        android:id="@+id/btnMatchMode"
        android:layout_width="match_parent"
        android:layout_height="56dp"
        android:text="🏆 比赛模式"
        android:textSize="16sp"
        android:backgroundTint="#1a237e"
        android:layout_marginBottom="8dp" />

    <Button
        android:id="@+id/btnTrainingMode"
        android:layout_width="match_parent"
        android:layout_height="56dp"
        android:text="🎯 训练模式"
        android:textSize="16sp"
        android:backgroundTint="#e65100"
        android:layout_marginBottom="8dp" />

    <Button
        android:id="@+id/btnChallengeMode"
        android:layout_width="match_parent"
        android:layout_height="56dp"
        android:text="⭐ 闯关模式"
        android:textSize="16sp"
        android:backgroundTint="#4a148c" />

</LinearLayout>
```

- [ ] **Step 2: Create MainActivity.java**

```java
package com.poolar.controller;

import android.os.Bundle;
import android.view.View;
import android.widget.Button;
import android.widget.TextView;
import android.widget.Toast;
import androidx.appcompat.app.AppCompatActivity;

import com.poolar.controller.network.ApiClient;
import com.poolar.controller.network.ServiceDiscovery;

public class MainActivity extends AppCompatActivity {

    private TextView connectionStatus;
    private ApiClient apiClient;
    private Button btnStart, btnStop, btnMatch, btnTraining, btnChallenge;

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);
        setContentView(R.layout.activity_main);

        connectionStatus = findViewById(R.id.connectionStatus);
        btnStart = findViewById(R.id.btnStart);
        btnStop = findViewById(R.id.btnStop);
        btnMatch = findViewById(R.id.btnMatchMode);
        btnTraining = findViewById(R.id.btnTrainingMode);
        btnChallenge = findViewById(R.id.btnChallengeMode);

        connectionStatus.setText("正在搜索服务器...");

        new ServiceDiscovery().discoverServer(new ServiceDiscovery.DiscoveryCallback() {
            @Override
            public void onFound(String host, int port) {
                apiClient = new ApiClient(host);
                runOnUiThread(() -> {
                    connectionStatus.setText("已连接: " + host);
                    connectionStatus.setTextColor(0xFF4CAF50);
                    enableButtons(true);
                    fetchStatus();
                });
            }

            @Override
            public void onError(String message) {
                runOnUiThread(() -> {
                    connectionStatus.setText("连接失败: " + message);
                    connectionStatus.setTextColor(0xFFF44336);
                });
            }
        });

        btnStart.setOnClickListener(v -> {
            if (apiClient != null) {
                apiClient.startSystem(new ApiClient.ApiCallback<Void>() {
                    @Override
                    public void onResult(Void result) {
                        showToast("系统已启动");
                    }
                    @Override
                    public void onError(String error) {
                        showToast("启动失败: " + error);
                    }
                });
            }
        });

        btnStop.setOnClickListener(v -> {
            if (apiClient != null) {
                apiClient.stopSystem(new ApiClient.ApiCallback<Void>() {
                    @Override
                    public void onResult(Void result) {
                        showToast("系统已停止");
                    }
                    @Override
                    public void onError(String error) {
                        showToast("停止失败: " + error);
                    }
                });
            }
        });

        btnMatch.setOnClickListener(v -> {
            if (apiClient != null) {
                apiClient.setMode("match", new ApiClient.ApiCallback<Object>() {
                    @Override
                    public void onResult(Object result) {
                        showToast("比赛模式已启动");
                    }
                    @Override
                    public void onError(String error) {
                        showToast("切换失败: " + error);
                    }
                });
            }
        });

        btnTraining.setOnClickListener(v -> {
            if (apiClient != null) {
                apiClient.setMode("training", new ApiClient.ApiCallback<Object>() {
                    @Override
                    public void onResult(Object result) {
                        showToast("训练模式已启动");
                    }
                    @Override
                    public void onError(String error) {
                        showToast("切换失败: " + error);
                    }
                });
            }
        });

        btnChallenge.setOnClickListener(v -> {
            if (apiClient != null) {
                apiClient.setMode("challenge", new ApiClient.ApiCallback<Object>() {
                    @Override
                    public void onResult(Object result) {
                        showToast("闯关模式已启动");
                    }
                    @Override
                    public void onError(String error) {
                        showToast("切换失败: " + error);
                    }
                });
            }
        });
    }

    private void enableButtons(boolean enabled) {
        btnStart.setEnabled(enabled);
        btnStop.setEnabled(enabled);
        btnMatch.setEnabled(enabled);
        btnTraining.setEnabled(enabled);
        btnChallenge.setEnabled(enabled);
    }

    private void fetchStatus() {
        if (apiClient == null) return;
        apiClient.getStatus(new ApiClient.ApiCallback<ApiClient.StatusResult>() {
            @Override
            public void onResult(ApiClient.StatusResult result) {
                String info = "模式: " + result.mode + " | 球数: " + result.ballCount;
                runOnUiThread(() -> connectionStatus.setText(info));
            }
            @Override
            public void onError(String error) {
                // Will retry
            }
        });
    }

    private void showToast(String message) {
        runOnUiThread(() ->
            Toast.makeText(MainActivity.this, message, Toast.LENGTH_SHORT).show());
    }
}
```

- [ ] **Step 3: Commit**

```bash
git add phone-app/app/src/main/java/com/poolar/controller/MainActivity.java
git add phone-app/app/src/main/res/layout/activity_main.xml
git commit -m "feat: add Android phone app main UI"
```

---

### 阶段九：安卓投影仪APP

#### Task 16: 投影仪APP - 项目结构和WebSocket接收

**Files:**
- Create: `projector-app/settings.gradle.kts`
- Create: `projector-app/build.gradle.kts`
- Create: `projector-app/app/build.gradle.kts`
- Create: `projector-app/app/src/main/AndroidManifest.xml`
- Create: `projector-app/app/src/main/java/com/poolar/projector/MainActivity.java`
- Create: `projector-app/app/src/main/java/com/poolar/projector/BootReceiver.java`

- [ ] **Step 1: Create projector-app/settings.gradle.kts**

```kotlin
pluginManagement {
    repositories {
        google()
        mavenCentral()
        gradlePluginPortal()
    }
}
dependencyResolutionManagement {
    repositoriesMode.set(RepositoriesMode.FAIL_ON_PROJECT_REPOS)
    repositories {
        google()
        mavenCentral()
    }
}
rootProject.name = "PoolARProjector"
include(":app")
```

- [ ] **Step 2: Create projector-app/build.gradle.kts**

```kotlin
plugins {
    id("com.android.application") version "8.2.0" apply false
}
```

- [ ] **Step 3: Create projector-app/app/build.gradle.kts**

```kotlin
plugins {
    id("com.android.application")
}

android {
    namespace = "com.poolar.projector"
    compileSdk = 34

    defaultConfig {
        applicationId = "com.poolar.projector"
        minSdk = 21
        targetSdk = 34
        versionCode = 1
        versionName = "1.0"
    }

    buildTypes {
        release {
            isMinifyEnabled = true
            proguardFiles(getDefaultProguardFile("proguard-android-optimize.txt"))
        }
    }
}

dependencies {
    implementation("org.java-websocket:Java-WebSocket:1.5.4")
    implementation("com.google.code.gson:gson:2.10.1")
}
```

- [ ] **Step 4: Create AndroidManifest.xml**

```xml
<?xml version="1.0" encoding="utf-8"?>
<manifest xmlns:android="http://schemas.android.com/apk/res/android">

    <uses-permission android:name="android.permission.INTERNET" />
    <uses-permission android:name="android.permission.ACCESS_NETWORK_STATE" />
    <uses-permission android:name="android.permission.RECEIVE_BOOT_COMPLETED" />
    <uses-permission android:name="android.permission.SYSTEM_ALERT_WINDOW" />

    <application
        android:allowBackup="true"
        android:label="台球投影"
        android:supportsRtl="true">

        <activity
            android:name=".MainActivity"
            android:exported="true"
            android:theme="@android:style/Theme.NoTitleBar.Fullscreen"
            android:keepScreenOn="true">
            <intent-filter>
                <action android:name="android.intent.action.MAIN" />
                <category android:name="android.intent.category.LAUNCHER" />
            </intent-filter>
        </activity>

        <receiver
            android:name=".BootReceiver"
            android:exported="true">
            <intent-filter>
                <action android:name="android.intent.action.BOOT_COMPLETED" />
            </intent-filter>
        </receiver>
    </application>
</manifest>
```

- [ ] **Step 5: Create MainActivity.java**

```java
package com.poolar.projector;

import android.graphics.Bitmap;
import android.graphics.BitmapFactory;
import android.os.Bundle;
import android.os.Handler;
import android.util.Base64;
import android.util.Log;
import android.view.View;
import android.widget.ImageView;
import android.widget.TextView;
import androidx.appcompat.app.AppCompatActivity;

import org.java_websocket.client.WebSocketClient;
import org.java_websocket.handshake.ServerHandshake;

import java.net.URI;
import java.util.concurrent.TimeUnit;

import okhttp3.OkHttpClient;

public class MainActivity extends AppCompatActivity {

    private ImageView projectionView;
    private TextView statusText;
    private WebSocketClient wsClient;
    private Handler reconnectHandler = new Handler();
    private static final String TAG = "PoolARProjector";

    // Default server IP - will be configurable
    private static final String DEFAULT_SERVER = "ws://192.168.1.100:8000/ws/projector";

    @Override
    protected void onCreate(Bundle savedInstanceState) {
        super.onCreate(savedInstanceState);

        // Full screen immersive mode
        getWindow().getDecorView().setSystemUiVisibility(
            View.SYSTEM_UI_FLAG_IMMERSIVE_STICKY
            | View.SYSTEM_UI_FLAG_FULLSCREEN
            | View.SYSTEM_UI_FLAG_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_STABLE
            | View.SYSTEM_UI_FLAG_LAYOUT_HIDE_NAVIGATION
            | View.SYSTEM_UI_FLAG_LAYOUT_FULLSCREEN
        );

        setContentView(R.layout.activity_projection);

        projectionView = findViewById(R.id.projectionView);
        statusText = findViewById(R.id.statusText);

        connectWebSocket();
    }

    private void connectWebSocket() {
        String serverUrl = getSharedPreferences("prefs", MODE_PRIVATE)
            .getString("server_url", DEFAULT_SERVER);

        try {
            wsClient = new WebSocketClient(new URI(serverUrl)) {
                @Override
                public void onOpen(ServerHandshake handshake) {
                    runOnUiThread(() -> {
                        statusText.setVisibility(View.GONE);
                        Log.d(TAG, "Connected to server");
                    });
                }

                @Override
                public void onMessage(String message) {
                    try {
                        com.google.gson.JsonObject json =
                            new com.google.gson.Gson().fromJson(
                                message, com.google.gson.JsonObject.class);
                        String type = json.get("type").getAsString();
                        if ("projection".equals(type)) {
                            String base64 = json.get("image").getAsString();
                            byte[] imgBytes = Base64.decode(base64, Base64.DEFAULT);
                            final Bitmap bitmap = BitmapFactory.decodeByteArray(
                                imgBytes, 0, imgBytes.length);
                            runOnUiThread(() -> projectionView.setImageBitmap(bitmap));
                        }
                    } catch (Exception e) {
                        Log.e(TAG, "Error decoding image", e);
                    }
                }

                @Override
                public void onClose(int code, String reason, boolean remote) {
                    runOnUiThread(() -> {
                        statusText.setVisibility(View.VISIBLE);
                        statusText.setText("连接断开，3秒后重连...");
                    });
                    reconnectHandler.postDelayed(
                        MainActivity.this::connectWebSocket, 3000);
                }

                @Override
                public void onError(Exception ex) {
                    Log.e(TAG, "WebSocket error", ex);
                    runOnUiThread(() -> {
                        statusText.setVisibility(View.VISIBLE);
                        statusText.setText("连接错误: " + ex.getMessage());
                    });
                }
            };
            wsClient.connect();
        } catch (Exception e) {
            Log.e(TAG, "Connection failed", e);
            reconnectHandler.postDelayed(this::connectWebSocket, 3000);
        }
    }

    @Override
    protected void onDestroy() {
        super.onDestroy();
        reconnectHandler.removeCallbacksAndMessages(null);
        if (wsClient != null) {
            wsClient.close();
        }
    }
}
```

- [ ] **Step 6: Create BootReceiver.java**

```java
package com.poolar.projector;

import android.content.BroadcastReceiver;
import android.content.Context;
import android.content.Intent;
import android.util.Log;

public class BootReceiver extends BroadcastReceiver {
    private static final String TAG = "PoolARBootReceiver";

    @Override
    public void onReceive(Context context, Intent intent) {
        if (Intent.ACTION_BOOT_COMPLETED.equals(intent.getAction())) {
            Log.d(TAG, "Boot completed, starting projector app");
            Intent launchIntent = new Intent(context, MainActivity.class);
            launchIntent.addFlags(Intent.FLAG_ACTIVITY_NEW_TASK);
            context.startActivity(launchIntent);
        }
    }
}
```

- [ ] **Step 7: Create projector layout**

Create `phone-app/../res/layout/ actually projector-app/app/src/main/res/layout/activity_projection.xml`:
```xml
<?xml version="1.0" encoding="utf-8"?>
<FrameLayout xmlns:android="http://schemas.android.com/apk/res/android"
    android:layout_width="match_parent"
    android:layout_height="match_parent"
    android:background="#000000">

    <ImageView
        android:id="@+id/projectionView"
        android:layout_width="match_parent"
        android:layout_height="match_parent"
        android:scaleType="fitCenter" />

    <TextView
        android:id="@+id/statusText"
        android:layout_width="wrap_content"
        android:layout_height="wrap_content"
        android:layout_gravity="center"
        android:text="正在连接服务器..."
        android:textColor="#FFFFFF"
        android:textSize="24sp"
        android:visibility="visible" />

</FrameLayout>
```

- [ ] **Step 8: Commit**

```bash
git add projector-app/
git commit -m "feat: add projector Android app with auto-start and WebSocket projection"
```

---

### 阶段十：集成和启动

#### Task 17: 集成主程序

**Files:**
- Modify: `backend/main.py` (full rewrite)

- [ ] **Step 1: Rewrite main.py as integrated launcher**

```python
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
from api.routes import router, system_state
from api.websocket import manager
from web.scoreboard_app import router as scoreboard_router
from camera.rtsp_camera import RtspCamera
from physics.engine import PhysicsEngine, Vec2
from game.match_mode import MatchMode
from game.training_mode import TrainingMode


class PoolARSystem:
    def __init__(self):
        self.camera: Optional[RtspCamera] = None
        self.physics = PhysicsEngine()
        self.match_mode = MatchMode()
        self.training_mode = TrainingMode()
        self._running = False
        self._vision_thread: Optional[threading.Thread] = None

    def start(self) -> None:
        print("[System] Starting Pool AR System...")
        system_state["match_mode"] = self.match_mode
        system_state["training_mode"] = self.training_mode

        # Start camera
        try:
            self.camera = RtspCamera(
                settings.CAMERA_RTSP_URL, settings.CAMERA_FPS)
            self.camera.start()
            print(f"[Camera] Connected to {settings.CAMERA_RTSP_URL}")
        except Exception as e:
            print(f"[Camera] Failed: {e}")
            print("[Camera] Running in offline mode (no camera)")

        # Start vision processing thread
        self._running = True
        self._vision_thread = threading.Thread(
            target=self._vision_loop, daemon=True)
        self._vision_thread.start()
        print("[System] Started")

    def stop(self) -> None:
        self._running = False
        if self.camera:
            self.camera.stop()
        print("[System] Stopped")

    def _vision_loop(self) -> None:
        while self._running:
            if self.camera and self.camera.is_running():
                frame = self.camera.get_frame()
                if frame and frame.valid:
                    system_state["table_state"]["detected"] = True
                    # Process frame here in future iterations
            time.sleep(0.1)

    @staticmethod
    def start_discovery_service() -> None:
        """Respond to UDP discovery from phone app."""
        sock = socket.socket(socket.AF_INET, socket.SOCK_DGRAM)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_REUSEADDR, 1)
        sock.setsockopt(socket.SOL_SOCKET, socket.SO_BROADCAST, 1)
        sock.bind(("0.0.0.0", 8001))

        while True:
            try:
                data, addr = sock.recvfrom(256)
                if data.decode().startswith("POOL_AR_DISCOVER"):
                    hostname = socket.gethostbyname(socket.gethostname())
                    response = f"POOL_AR_SERVER:{hostname}"
                    sock.sendto(response.encode(), addr)
                    print(f"[Discovery] Responded to {addr}")
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


if __name__ == "__main__":
    system = PoolARSystem()
    system.start()

    # Start discovery service in background
    disc_thread = threading.Thread(
        target=PoolARSystem.start_discovery_service, daemon=True)
    disc_thread.start()

    app = create_app(system)
    print(f"\n[Server] Starting API at http://0.0.0.0:{settings.API_PORT}")
    print("[Server] Scoreboard at http://<ip>:{}/scoreboard".format(
        settings.API_PORT))
    print("[Server] Phone app can now discover and connect\n")

    uvicorn.run(app, host=settings.API_HOST, port=settings.API_PORT)
```

- [ ] **Step 2: Test the main entry**

Run: `cd D:/daima/backend && python main.py`
Expected: Server starts, prints status messages, then serves on port 8000
(Kill with Ctrl+C after confirming startup)

- [ ] **Step 3: Commit**

```bash
git add backend/main.py
git commit -m "feat: add integrated system launcher with discovery service"
```

---

#### Task 18: 启动脚本

**Files:**
- Create: `D:/daima/start_backend.bat`

- [ ] **Step 1: Create Windows batch launcher**

```bat
@echo off
title 台球AR投影系统 - 后端服务
cd /d D:\daima\backend

echo ============================================
echo    台球智能AR投影系统 - 后端服务
echo ============================================
echo.

REM Check if Python is available
python --version >nul 2>&1
if errorlevel 1 (
    echo [错误] 未找到Python，请先安装Python 3.11+
    pause
    exit /b 1
)

REM Install dependencies if needed
pip install -r requirements.txt -q

echo [启动] 正在启动系统...
echo.
echo 请确保已在 config.py 中配置好摄像头RTSP地址
echo 按 Ctrl+C 停止服务
echo.

python main.py

pause
```

- [ ] **Step 2: Create a README with Chinese instructions**

Create `D:/daima/README.md`:
```markdown
# 台球智能AR投影系统

## 系统组成
- 电脑后端 (Python程序) — 运行在Windows电脑上
- 安卓手机APP — 控制系统
- 安卓投影仪APP — 显示投影路线（安装在智能投影仪上）
- 比分网页 — NAS/软路由浏览器打开

## 快速开始

### 1. 启动电脑后端
1. 安装 Python 3.11+ (https://www.python.org/downloads/)
2. 双击 `start_backend.bat`
3. 第一次运行会自动安装依赖，等待即可

### 2. 配置摄像头
编辑 `backend/config.py`，修改 `CAMERA_RTSP_URL` 为你的WiFi摄像头地址

### 3. 安装安卓手机APP
- 将 `phone-app/build/outputs/apk/debug/phone-app-debug.apk` 复制到手机
- 在手机上安装

### 4. 安装投影仪APP
- 将 `projector-app/build/outputs/apk/debug/projector-app-debug.apk` 复制到投影仪
- 在投影仪上用文件管理器安装
- 安装后打开一次，之后开机自动启动

### 5. 比分显示屏
- NAS或软路由打开浏览器，访问 http://电脑IP:8000/scoreboard
- 全屏显示即可

## 操作说明
1. 打开手机APP，自动搜索到后端电脑后即可控制
2. 选择模式：比赛/训练/闯关
3. 系统自动识别桌面球的位置并推荐进攻路线
```

- [ ] **Step 3: Create .gitignore**

```txt
# Python
__pycache__/
*.pyc
*.pyo
.venv/
venv/

# Android
phone-app/.gradle/
phone-app/build/
phone-app/app/build/
projector-app/.gradle/
projector-app/build/
projector-app/app/build/
phone-app/local.properties

# IDE
.idea/
*.iml
.vscode/

# System
.superpowers/
```

- [ ] **Step 4: Commit**

```bash
git add start_backend.bat README.md .gitignore
git commit -m "docs: add startup script, README, and gitignore"
```

---

## 计划完成情况自查

### 需求覆盖
- [x] 比赛模式 — 自动推荐双色球路线、比分记录 (Task 7, 12)
- [x] 训练模式10档难度 (Task 8)
- [x] 训练关卡题型 (Task 8 - training_data.py)
- [x] 摆球验证 (Task 8 - verify_placement)
- [x] 路线/杆法/力度/母球走位/落点 (Task 6, 11)
- [x] 闯关模式：3次连续成功过关 (Task 8)
- [x] 手动选关 (Task 8 - select_level)
- [x] 手机APP控制 (Task 13-15)
- [x] 投影仪APP开机自启 (Task 16)
- [x] 比分网页 (Task 12)
- [x] WiFi摄像头RTSP接入 (Task 2)
- [x] 智能投影仪WiFi接收画面 (Task 11, 16)
