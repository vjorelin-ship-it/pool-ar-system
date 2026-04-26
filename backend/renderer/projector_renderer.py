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

    COLORS = {
        "cue_line": (100, 200, 255),
        "target_line": (255, 200, 50),
        "cue_ball": (255, 255, 200),
        "target_ball": (255, 100, 50),
        "text": (255, 255, 255),
        "landing_zone": (100, 255, 100, 80),
        "calibration": (0, 255, 0),
        "calibration_cross": (255, 0, 0),
    }

    TABLE_LEFT = 200
    TABLE_TOP = 80
    TABLE_RIGHT = 1720
    TABLE_BOTTOM = 1000
    TABLE_WIDTH = TABLE_RIGHT - TABLE_LEFT
    TABLE_HEIGHT = TABLE_BOTTOM - TABLE_TOP

    def __init__(self):
        self._image = Image.new("RGB", (self.WIDTH, self.HEIGHT), (0, 0, 0))
        self._draw = ImageDraw.Draw(self._image, "RGBA")

    def render(self, overlay: Optional[ProjectionOverlay] = None) -> bytes:
        """Render route lines on black background for projection overlay."""
        self._clear()
        self._draw_table_outline()
        if overlay:
            self._draw_shot(overlay)
        buf = io.BytesIO()
        self._image.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    def render_calibration(self, markers: List[Tuple[float, float]]) -> bytes:
        """Render calibration markers (crosshairs at given normalized coords)."""
        self._clear()
        for mx, my in markers:
            px, py = self._norm_to_proj((mx, my))
            size = 30
            # Crosshair
            self._draw.line(
                [px - size, py, px + size, py],
                fill=self.COLORS["calibration_cross"], width=3,
            )
            self._draw.line(
                [px, py - size, px, py + size],
                fill=self.COLORS["calibration_cross"], width=3,
            )
            # Circle around crosshair
            self._draw.ellipse(
                [px - size, py - size, px + size, py + size],
                outline=self.COLORS["calibration"], width=2,
            )
        # Draw table outline
        self._draw.rectangle(
            [self.TABLE_LEFT, self.TABLE_TOP, self.TABLE_RIGHT, self.TABLE_BOTTOM],
            outline=(80, 80, 80), width=2,
        )
        buf = io.BytesIO()
        self._image.save(buf, format="JPEG", quality=85)
        return buf.getvalue()

    def render_to_base64(self, overlay: Optional[ProjectionOverlay] = None) -> str:
        jpeg_bytes = self.render(overlay)
        return base64.b64encode(jpeg_bytes).decode("utf-8")

    def render_calibration_to_base64(self, markers: List[Tuple[float, float]]) -> str:
        jpeg_bytes = self.render_calibration(markers)
        return base64.b64encode(jpeg_bytes).decode("utf-8")

    def _clear(self) -> None:
        self._draw.rectangle([0, 0, self.WIDTH, self.HEIGHT], fill=(0, 0, 0))

    def _draw_table_outline(self) -> None:
        """Draw subtle table outline and pocket markers for standby display."""
        outline_color = (40, 40, 40)
        # Table border
        self._draw.rectangle(
            [self.TABLE_LEFT, self.TABLE_TOP, self.TABLE_RIGHT, self.TABLE_BOTTOM],
            outline=outline_color, width=1,
        )
        # Diamond markers on rails (small ticks)
        for x_frac in [0.25, 0.5, 0.75]:
            x = self.TABLE_LEFT + x_frac * self.TABLE_WIDTH
            self._draw.line([x, self.TABLE_TOP - 5, x, self.TABLE_TOP + 5], fill=outline_color, width=1)
            self._draw.line([x, self.TABLE_BOTTOM - 5, x, self.TABLE_BOTTOM + 5], fill=outline_color, width=1)
        for y_frac in [0.25, 0.5, 0.75]:
            y = self.TABLE_TOP + y_frac * self.TABLE_HEIGHT
            self._draw.line([self.TABLE_LEFT - 5, y, self.TABLE_LEFT + 5, y], fill=outline_color, width=1)
            self._draw.line([self.TABLE_RIGHT - 5, y, self.TABLE_RIGHT + 5, y], fill=outline_color, width=1)
        # Pocket circles
        pockets = [
            (self.TABLE_LEFT, self.TABLE_TOP),
            (self.WIDTH // 2, self.TABLE_TOP),
            (self.TABLE_RIGHT, self.TABLE_TOP),
            (self.TABLE_LEFT, self.TABLE_BOTTOM),
            (self.WIDTH // 2, self.TABLE_BOTTOM),
            (self.TABLE_RIGHT, self.TABLE_BOTTOM),
        ]
        for px, py in pockets:
            r = 18
            self._draw.ellipse(
                [px - r, py - r, px + r, py + r],
                outline=outline_color, width=1,
            )
        # Standby text
        self._draw.text(
            (self.WIDTH // 2 - 40, self.TABLE_BOTTOM + 40),
            "待机中", fill=(60, 60, 60),
        )

    def _draw_shot(self, overlay: ProjectionOverlay) -> None:
        if len(overlay.cue_path) >= 2:
            pts = [self._norm_to_proj(p) for p in overlay.cue_path]
            for i in range(len(pts) - 1):
                self._draw.line(
                    [pts[i], pts[i + 1]],
                    fill=self.COLORS["cue_line"], width=4,
                )

        if len(overlay.target_path) >= 2:
            pts = [self._norm_to_proj(p) for p in overlay.target_path]
            for i in range(len(pts) - 1):
                self._draw.line(
                    [pts[i], pts[i + 1]],
                    fill=self.COLORS["target_line"], width=4,
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
                overlay.label, fill=self.COLORS["text"], font=None,
            )

        # Render cue technique and power
        tech_parts = []
        if overlay.cue_technique:
            tech_parts.append(f"杆法: {overlay.cue_technique}")
        if overlay.cue_power:
            tech_parts.append(f"力度: {overlay.cue_power}")
        if tech_parts:
            self._draw.text(
                (self.TABLE_LEFT + 10, self.TABLE_BOTTOM + 60),
                " | ".join(tech_parts),
                fill=(200, 200, 100),
            )

    def _norm_to_proj(self, pos: Tuple[float, float]) -> Tuple[int, int]:
        x, y = pos
        px = self.TABLE_LEFT + x * self.TABLE_WIDTH
        py = self.TABLE_TOP + y * self.TABLE_HEIGHT
        return (int(px), int(py))
