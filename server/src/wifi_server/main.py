import os

import uvicorn
from fastapi import FastAPI

from wifi_server.api.agents import router as agents_router
from wifi_server.api.analyses import router as analyses_router
from wifi_server.api.projects import router as projects_router
from wifi_server.api.recordings import router as recordings_router
from wifi_server.api.reports import router as reports_router

app = FastAPI(title="Wi-Fi Experience Monitor Server", version="0.1.0")
app.include_router(agents_router)
app.include_router(recordings_router)
app.include_router(analyses_router)
app.include_router(projects_router)
app.include_router(reports_router)


@app.get("/health")
def health() -> dict[str, str]:
    return {"status": "ok"}


def main() -> None:
    uvicorn.run(
        "wifi_server.main:app",
        host=os.getenv("SERVER_HOST", "127.0.0.1"),
        port=int(os.getenv("SERVER_PORT", "8000")),
        reload=False,
    )
