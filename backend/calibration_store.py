"""校准结果持久化

保存/加载投影仪-摄像头坐标映射数据，避免每次开机重新校准。
使用原子写入防止文件损坏。
"""
import json
import os
from typing import Optional, List, Tuple

CALIBRATION_FILE = os.path.join(os.path.dirname(__file__), "calibration_data.json")


def save_calibration(corners: List[Tuple[float, float]],
                     homography: Optional[List[List[float]]] = None,
                     markers: Optional[List[Tuple[float, float]]] = None) -> bool:
    """原子写入校准结果"""
    data = {
        "corners": [[float(x), float(y)] for x, y in corners],
        "homography": [list(row) for row in homography] if homography else [],
        "markers": [[float(x), float(y)] for x, y in markers] if markers else [],
    }
    try:
        tmp = CALIBRATION_FILE + ".tmp"
        with open(tmp, "w") as f:
            json.dump(data, f, indent=2)
        os.replace(tmp, CALIBRATION_FILE)
        return True
    except (OSError, PermissionError) as e:
        print(f"[Calibration] Save failed: {e}")
        return False


def load_calibration() -> Optional[dict]:
    """加载校准结果，不存在或损坏时返回None"""
    if not os.path.exists(CALIBRATION_FILE):
        return None
    try:
        with open(CALIBRATION_FILE, "r") as f:
            return json.load(f)
    except (json.JSONDecodeError, OSError, PermissionError) as e:
        print(f"[Calibration] Load failed (corrupted?): {e}")
        return None


def clear_calibration() -> None:
    """清除校准数据"""
    try:
        if os.path.exists(CALIBRATION_FILE):
            os.remove(CALIBRATION_FILE)
        tmp = CALIBRATION_FILE + ".tmp"
        if os.path.exists(tmp):
            os.remove(tmp)
    except OSError as e:
        print(f"[Calibration] Clear failed: {e}")
