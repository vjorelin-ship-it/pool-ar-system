import base64
import io
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
    cue_technique: str = ""
    cue_power: int = 50
    cue_final_pos: Optional[Tuple[float, float]] = None
    label: str = ""


class ProjectorRenderer:
    WIDTH = 1920
    HEIGHT = 1080

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
        "cue_line": (100, 200, 255),
        "target_line": (255, 200, 50),
        "cue_ball": (255, 255, 200),
        "target_ball": (255, 100, 50),
        "text": (255, 255, 255),
        "landing_zone": (100, 255, 100, 80),
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
        margin = 20
        self._draw.rectangle(
            [self.TABLE_LEFT - margin, self.TABLE_TOP - margin,
             self.TABLE_RIGHT + margin, self.TABLE_BOTTOM + margin],
            fill=self.COLORS["cushion"],
        )
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
        mid_x = (self.TABLE_LEFT + self.TABLE_RIGHT) // 2
        for cy in (self.TABLE_TOP, self.TABLE_BOTTOM):
            self._draw.ellipse(
                [mid_x - r, cy - r, mid_x + r, cy + r],
                fill=self.COLORS["pocket"],
            )

    def _draw_shot(self, overlay: ProjectionOverlay) -> None:
        if len(overlay.cue_path) >= 2:
            pts = [self._norm_to_proj(p) for p in overlay.cue_path]
            for i in range(len(pts) - 1):
                self._draw.line(
                    [pts[i], pts[i + 1]],
                    fill=self.COLORS["cue_line"],
                    width=4,
                )

        if len(overlay.target_path) >= 2:
            pts = [self._norm_to_proj(p) for p in overlay.target_path]
            for i in range(len(pts) - 1):
                self._draw.line(
                    [pts[i], pts[i + 1]],
                    fill=self.COLORS["target_line"],
                    width=4,
                )

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

        pocket_px = self._norm_to_proj(overlay.pocket)
        pr = 30
        self._draw.ellipse(
            [pocket_px[0] - pr, pocket_px[1] - pr,
             pocket_px[0] + pr, pocket_px[1] + pr],
            outline=(255, 255, 0), width=3,
        )

        if overlay.cue_final_pos:
            lp = self._norm_to_proj(overlay.cue_final_pos)
            lr = 20
            self._draw.ellipse(
                [lp[0] - lr, lp[1] - lr, lp[0] + lr, lp[1] + lr],
                fill=self.COLORS["landing_zone"],
            )

        if overlay.label:
            self._draw.text(
                (self.TABLE_LEFT + 10, self.TABLE_BOTTOM + 30),
                overlay.label,
                fill=self.COLORS["text"],
            )

    def _norm_to_proj(self, pos: Tuple[float, float]) -> Tuple[int, int]:
        x, y = pos
        px = self.TABLE_LEFT + x * self.TABLE_WIDTH
        py = self.TABLE_TOP + y * self.TABLE_HEIGHT
        return (int(px), int(py))
