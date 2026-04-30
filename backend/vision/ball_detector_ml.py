"""
ML-based ball detector using YOLOv8.
Replaces HoughCircles + color classification with a lightweight neural network.
"""
import os
from typing import List, Optional, Tuple
import numpy as np

from .ball_detector import Ball

# YOLO class mapping for Chinese 8-ball
# 0=cue(white), 1-7=solids, 8=black(8-ball), 9-15=stripes
SOLID_IDS = set(range(1, 8))    # yellow, blue, red, purple, orange, green, brown
STRIPE_IDS = set(range(9, 16))  # same colors striped
BLACK_ID = 8
CUE_ID = 0

CLASS_NAMES = {
    0: "white", 1: "yellow", 2: "blue", 3: "red", 4: "purple",
    5: "orange", 6: "green", 7: "brown", 8: "black",
    9: "yellow", 10: "blue", 11: "red", 12: "purple",
    13: "orange", 14: "green", 15: "brown",
}


class BallDetectorML:
    """YOLOv8 / ONNX-based pool ball detector.
    Supports both PyTorch (ultralytics) and ONNX Runtime with DirectML.

    Usage:
        detector = BallDetectorML()
        detector.load("backend/learning/balls.pt")  # PyTorch
        detector.load("backend/learning/balls.onnx")  # ONNX+DirectML
        balls = detector.detect(warped_image)
    """

    def __init__(self, conf_threshold: float = 0.25):
        self._model = None
        self._onnx_session = None
        self._onnx_input_name = None
        self._onnx_input_size = (640, 640)
        self._conf = conf_threshold
        self._loaded = False

    def load(self, model_path: str) -> bool:
        """Load a trained model. Supports .pt (ultralytics) and .onnx (ONNX Runtime)."""
        try:
            if model_path.endswith(".onnx"):
                return self._load_onnx(model_path)
            else:
                return self._load_ultralytics(model_path)
        except Exception as e:
            print(f"[BallDetectML] Failed to load model: {e}")
            self._loaded = False
            return False

    def _load_ultralytics(self, path: str) -> bool:
        from ultralytics import YOLO
        self._model = YOLO(path)
        self._loaded = True
        print(f"[BallDetectML] Loaded YOLO model: {path}")
        return True

    def _load_onnx(self, path: str) -> bool:
        try:
            from learning.gpu_device import get_ort_providers
            import onnxruntime as ort
        except ImportError:
            print("[BallDetectML] onnxruntime not installed")
            return False
        providers = get_ort_providers()
        self._onnx_session = ort.InferenceSession(path, providers=providers)
        self._onnx_input_name = self._onnx_session.get_inputs()[0].name
        print(f"[BallDetectML] Loaded ONNX model: {path} (providers={providers})")
        self._loaded = True
        return True

    def is_loaded(self) -> bool:
        return self._loaded

    def detect(self, warped) -> List[Ball]:
        """Run inference on the warped table image."""
        if not self._loaded:
            return []

        if self._onnx_session is not None:
            return self._detect_onnx(warped)
        else:
            return self._detect_ultralytics(warped)

    def _detect_ultralytics(self, warped) -> List[Ball]:
        if self._model is None:
            return []
        h, w = warped.shape[:2]
        results = self._model(warped, conf=self._conf, verbose=False)
        balls = []

        for r in results:
            if r.boxes is None:
                continue
            boxes = r.boxes.xywh.cpu().numpy()
            classes = r.boxes.cls.cpu().numpy().astype(int)
            confs = r.boxes.conf.cpu().numpy()

            for (cx, cy, bw, bh), cls_id, conf in zip(boxes, classes, confs):
                ball = self._box_to_ball(cx, cy, bw, bh, cls_id, w, h, float(conf))
                if ball:
                    balls.append(ball)
        return balls

    def _detect_onnx(self, warped) -> List[Ball]:
        import cv2
        h, w = warped.shape[:2]
        # Preprocess: resize + normalize
        img = cv2.resize(warped, self._onnx_input_size)
        img = cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
        img = img.astype(np.float32) / 255.0
        img = np.transpose(img, (2, 0, 1))  # HWC -> CHW
        img = np.expand_dims(img, axis=0)   # add batch dim

        outputs = self._onnx_session.run(None, {self._onnx_input_name: img})
        # YOLOv8 ONNX output: (1, 84, 8400) — [x,y,w,h, class_0,...,class_15] * 8400
        preds = outputs[0][0]  # shape (84, 8400)
        preds = np.transpose(preds)  # (8400, 84)

        balls = []
        for pred in preds:
            cx, cy, bw, bh = pred[:4]
            scores = pred[4:20]  # 16 classes
            cls_id = int(np.argmax(scores))
            conf = float(scores[cls_id])
            if conf < self._conf:
                continue
            ball = self._box_to_ball(cx, cy, bw, bh, cls_id, w, h, conf)
            if ball:
                balls.append(ball)
        return balls

    @staticmethod
    def _box_to_ball(cx: float, cy: float, bw: float, bh: float,
                     cls_id: int, img_w: int, img_h: int,
                     conf: float) -> Optional[Ball]:
        """Convert YOLO output to Ball dataclass."""
        # Normalize coordinates to [0,1]
        nx = cx / img_w
        ny = cy / img_h
        radius = max(bw, bh) / 2.0

        if cls_id == CUE_ID:
            return Ball(x=float(nx), y=float(ny), radius=float(radius),
                        color="white", is_cue=True,
                        is_solid=False, is_stripe=False, is_black=False)
        elif cls_id == BLACK_ID:
            return Ball(x=float(nx), y=float(ny), radius=float(radius),
                        color="black", is_cue=False,
                        is_solid=False, is_stripe=False, is_black=True)
        elif cls_id in SOLID_IDS:
            color = CLASS_NAMES.get(cls_id, "unknown")
            return Ball(x=float(nx), y=float(ny), radius=float(radius),
                        color=color, is_cue=False,
                        is_solid=True, is_stripe=False, is_black=False)
        elif cls_id in STRIPE_IDS:
            color = CLASS_NAMES.get(cls_id, "unknown")
            return Ball(x=float(nx), y=float(ny), radius=float(radius),
                        color=color, is_cue=False,
                        is_solid=False, is_stripe=True, is_black=False)

        return None
