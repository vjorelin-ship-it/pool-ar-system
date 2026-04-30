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


@router.get("/projector-sim", response_class=HTMLResponse)
async def get_projector_sim():
    html = TEMPLATES_DIR / "projector_sim.html"
    if not html.exists():
        return HTMLResponse("<h1>Projector simulation not found</h1>", status_code=404)
    return HTMLResponse(html.read_text(encoding="utf-8"))


@router.get("/annotate", response_class=HTMLResponse)
async def get_annotate():
    html = TEMPLATES_DIR / "annotate.html"
    if not html.exists():
        return HTMLResponse("<h1>Annotation tool not found</h1>", status_code=404)
    return HTMLResponse(html.read_text(encoding="utf-8"))


@router.get("/admin", response_class=HTMLResponse)
async def get_admin():
    """管理控制台 — 系统控制、数据采集、模型训练、标注、校准一体化页面"""
    html = TEMPLATES_DIR / "admin.html"
    if not html.exists():
        return HTMLResponse("<h1>Admin panel not found</h1>", status_code=404)
    return HTMLResponse(html.read_text(encoding="utf-8"))
