import os

import uvicorn
from fastapi import FastAPI

from wifi_server.api.agents import router as agents_router

app = FastAPI(title="Wi-Fi Experience Monitor Server", version="0.1.0")
app.include_router(agents_router)


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
