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
