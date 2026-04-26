from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from contextlib import asynccontextmanager


@asynccontextmanager
async def lifespan(app: FastAPI):
    # Startup
    print("[API] Server starting...")
    yield
    # Shutdown
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

    @app.get("/api/status")
    async def get_status():
        return {"status": "running", "version": "1.0.0"}

    return app
