import os


class Settings:
    # Camera
    CAMERA_RTSP_URL: str = os.getenv("CAMERA_RTSP_URL", "rtsp://192.168.0.101:554/stream1")
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
