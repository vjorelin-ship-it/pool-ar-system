"""击球选手识别模块

通过采样选手衣服颜色特征，在击球时识别是哪位选手在打球。
用于裁判执裁——判断是否打错球、轮次错误。

原理：
  注册阶段：选手站在桌边指定位置 → 采集衣服区域HSV颜色直方图
  检测阶段：杆速检测触发 → 提取母球附近桌面边缘颜色 → 匹配选手

CTBA规则要求 — 裁判需要确认击球选手身份才能判罚：
  - 打错球（打对方的球）
  - 轮次错误（该对方打但你打了）
"""

from typing import Optional, Tuple
import numpy as np
import cv2


class PlayerIdentifier:
    """选手识别器"""

    def __init__(self):
        self._player1_features: Optional[dict] = None
        self._player2_features: Optional[dict] = None
        self._registered = False
        self._last_identified: Optional[int] = None  # 1 or 2

    @property
    def is_registered(self) -> bool:
        return self._registered

    def register_from_edge(self, warped_frame: np.ndarray,
                           player: int, edge: str = "bottom") -> bool:
        """注册选手：从桌面俯视图的边缘区域采样选手衣服颜色。

        Args:
            warped_frame: 桌面俯视图 BGR
            player: 1 或 2
            edge: 采样边缘 'top'/'bottom'/'left'/'right'

        Returns:
            是否注册成功
        """
        h, w = warped_frame.shape[:2]
        region = self._get_edge_region(warped_frame, h, w, edge)
        if region is None or region.size == 0:
            return False

        hist = self._compute_hsv_histogram(region)
        dominant = self._get_dominant_color(region)
        features = {"hist": hist, "dominant": dominant, "edge": edge}

        if player == 1:
            self._player1_features = features
        else:
            self._player2_features = features
        self._registered = (self._player1_features is not None and
                            self._player2_features is not None)
        name = "选手一" if player == 1 else "选手二"
        hsv = dominant
        print(f"[PlayerID] {name} 注册完成 — 主导色 HSV=({hsv[0]:.0f},{hsv[1]:.0f},{hsv[2]:.0f})")
        return True

    def identify(self, warped_frame: np.ndarray,
                 cue_ball_pos: Tuple[float, float]) -> Optional[int]:
        """识别当前击球选手。

        在杆速检测触发击球时调用，提取母球附近的衣服颜色匹配。

        Args:
            warped_frame: 桌面俯视图 BGR
            cue_ball_pos: 母球位置 (x, y) 归一化坐标 [0,1]

        Returns:
            1 或 2（选手编号），None（无法确定）
        """
        if not self._registered:
            return self._last_identified

        h, w = warped_frame.shape[:2]
        # 母球像素坐标
        cx = int(cue_ball_pos[0] * w)
        cy = int(cue_ball_pos[1] * h)

        # 根据母球位置判断选手可能在哪个方向
        # 母球靠下 → 选手在下方 → 采样底部边缘
        if cy > h * 0.6:
            edge = "bottom"
        elif cy < h * 0.4:
            edge = "top"
        elif cx < w * 0.4:
            edge = "left"
        else:
            edge = "right"

        region = self._get_edge_region(warped_frame, h, w, edge)
        if region is None or region.size == 0:
            return self._last_identified

        hist = self._compute_hsv_histogram(region)

        # 与两个选手特征比较
        sim1 = self._compare_hist(hist, self._player1_features["hist"])
        sim2 = self._compare_hist(hist, self._player2_features["hist"])

        if max(sim1, sim2) < 0.4:  # 差异太小，无法确定
            return self._last_identified

        result = 1 if sim1 > sim2 else 2
        self._last_identified = result
        return result

    @staticmethod
    def _get_edge_region(frame: np.ndarray, h: int, w: int,
                         edge: str) -> Optional[np.ndarray]:
        """提取桌面边缘区域（选手身体/衣服会出现的区域）"""
        margin = int(min(h, w) * 0.12)  # 12% margin
        if edge == "bottom":
            return frame[h - margin:h, w // 4: 3 * w // 4]
        elif edge == "top":
            return frame[0:margin, w // 4: 3 * w // 4]
        elif edge == "left":
            return frame[h // 4: 3 * h // 4, 0:margin]
        elif edge == "right":
            return frame[h // 4: 3 * h // 4, w - margin:w]
        return None

    @staticmethod
    def _compute_hsv_histogram(bgr: np.ndarray) -> np.ndarray:
        """计算HSV颜色直方图"""
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        hist = cv2.calcHist([hsv], [0, 1], None, [30, 32], [0, 180, 0, 256])
        cv2.normalize(hist, hist, 0, 1, cv2.NORM_MINMAX)
        return hist

    @staticmethod
    def _get_dominant_color(bgr: np.ndarray) -> Tuple[int, int, int]:
        """返回主导HSV颜色"""
        hsv = cv2.cvtColor(bgr, cv2.COLOR_BGR2HSV)
        h_mean = int(np.mean(hsv[:, :, 0]))
        s_mean = int(np.mean(hsv[:, :, 1]))
        v_mean = int(np.mean(hsv[:, :, 2]))
        return (h_mean, s_mean, v_mean)

    @staticmethod
    def _compare_hist(h1: np.ndarray, h2: np.ndarray) -> float:
        """比较两个直方图的相似度 (0~1, 越高越相似)"""
        return float(cv2.compareHist(h1, h2, cv2.HISTCMP_CORREL))
