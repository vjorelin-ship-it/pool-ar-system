import os


class Settings:
    # Camera
    CAMERA_RTSP_URL: str = os.getenv("CAMERA_RTSP_URL", "")
    CAMERA_FPS: int = 10
    CAMERA_SOURCE = os.getenv("CAMERA_SOURCE", "rtsp")  # "rtsp" | "websocket"

    # Server
    API_HOST: str = "0.0.0.0"
    API_PORT: int = 8000


settings = Settings()
if not settings.CAMERA_RTSP_URL:
    print("[Config] WARNING: CAMERA_RTSP_URL environment variable not set. Camera will not work.")
