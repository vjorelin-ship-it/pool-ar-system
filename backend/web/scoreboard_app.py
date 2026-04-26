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
