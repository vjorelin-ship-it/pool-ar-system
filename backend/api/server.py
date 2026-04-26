from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager
from .routes import router
from web.scoreboard_app import router as scoreboard_router


@asynccontextmanager
async def lifespan(app: FastAPI):
    print("[API] Server starting...")
    yield
    print("[API] Server shutting down...")


def create_app() -> FastAPI:
    app = FastAPI(
        title="Pool AR System API",
        version="1.0.0",
        lifespan=lifespan,
    )

    app.add_middleware(
        CORSMiddleware,
        allow_origins=["*"],
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    app.include_router(router)
    app.include_router(scoreboard_router)

    return app
