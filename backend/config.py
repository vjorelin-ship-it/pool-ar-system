import os


class Settings:
    # Camera
    CAMERA_RTSP_URL: str = os.getenv("CAMERA_RTSP_URL", "")
    CAMERA_FPS: int = 10
    CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "rtsp")  # "rtsp" | "websocket"

    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000

    # Training data directories
    BALL_ML_DATA_DIR: str = os.getenv(
        "BALL_ML_DATA_DIR",
        os.path.join(os.path.dirname(__file__), "learning", "training_data"),
    )
    TRAJECTORY_DATA_DIR: str = os.getenv(
        "TRAJECTORY_DATA_DIR",
        os.path.join(os.path.dirname(__file__), "learning", "collected_shots"),
    )


settings = Settings()
if not settings.CAMERA_RTSP_URL:
    print("[Config] WARNING: CAMERA_RTSP_URL environment variable not set. Camera will not work.")
