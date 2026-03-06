"""Model service: app factory, lifespan, CORS."""
from contextlib import asynccontextmanager

import httpx
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from router import router
from service import fetch_schema, load_few_shots, log_event


@asynccontextmanager
async def lifespan(app: FastAPI):
    async with httpx.AsyncClient(timeout=30) as client:
        log_event("INFO", "startup", detail="Fetching schema from db-service")
        app.state.schema = await fetch_schema(client)
        app.state.few_shots = load_few_shots()
        app.state.http_client = client
        log_event("INFO", "startup_complete",
                  columns=[c["name"] for c in app.state.schema.get("columns", [])])
        yield


app = FastAPI(lifespan=lifespan)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173"],
    allow_methods=["POST", "GET"],
    allow_headers=["Content-Type"],
)

app.include_router(router)
