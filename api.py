"""FastAPI backend for the React frontend.

Endpoints:
    POST /api/run                {idea} -> {run_id} (starts background thread)
    GET  /api/stream/{run_id}    Server-Sent Events: agent logs, images, done
    GET  /api/image/{run_id}/{f} generated images
Mounts frontend/dist at "/" if you built the React app (`npm run build`).
"""

import json
import queue
import threading
import uuid
from datetime import datetime
from pathlib import Path

from dotenv import load_dotenv
load_dotenv()

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, StreamingResponse
from fastapi.staticfiles import StaticFiles
from pydantic import BaseModel

from pipeline.graph import app
from pipeline.images import iter_images

RUNS_DIR = Path("outputs")
RUNS_DIR.mkdir(exist_ok=True)

# run_id -> {"queue": queue.Queue} ; simple in-memory registry, fine for local use
RUNS: dict[str, dict] = {}

api = FastAPI(title="Content Pipeline API")

# Local dev: allow the Vite server (it also proxies /api, belt and braces).
api.add_middleware(
    CORSMiddleware,
    allow_origins=["http://localhost:5173", "http://127.0.0.1:5173"],
    allow_methods=["*"],
    allow_headers=["*"],
)


class RunRequest(BaseModel):
    idea: str


@api.post("/api/run")
def start_run(req: RunRequest):
    idea = req.idea.strip()
    if not idea:
        raise HTTPException(status_code=400, detail="Idea must not be empty")
    run_id = uuid.uuid4().hex[:10]
    image_dir = RUNS_DIR / f"react-{run_id}" / "images"
    RUNS[run_id] = {"queue": queue.Queue()}
    threading.Thread(
        target=_execute, args=(run_id, idea, image_dir), daemon=True
    ).start()
    return {"run_id": run_id}


def _execute(run_id: str, idea: str, image_dir: Path) -> None:
    """Run the pipeline + images in a thread, emitting JSON queue events."""
    q = RUNS[run_id]["queue"]
    try:
        final = None
        for chunk in app.stream(
            {"topic": idea}, config={"recursion_limit": 60}, stream_mode="updates"
        ):
            for node, update in chunk.items():
                if not update:
                    continue
                for line in update.get("run_log", []):
                    q.put(json.dumps({"type": "log", "node": node, "line": line}))
                if "final" in update:
                    final = update["final"]

        if final is None:
            q.put(json.dumps({"type": "error", "message": "Pipeline produced no result"}))
            return

        posts_json = [p.model_dump() for p in final.posts]
        published = [p for p in final.posts if p.pipeline_result == "published"]
        q.put(json.dumps({"type": "posts", "posts": posts_json,
                          "published": len(published)}))

        # Images stream in one by one (free tier pacing happens inside).
        run_dir_rel = None
        for index, path in iter_images(final, image_dir):
            run_dir_rel = f"/api/image/{run_id}/{path.name}"
            q.put(json.dumps({"type": "image", "index": index, "url": run_dir_rel}))
        if len(published) and run_dir_rel is None:
            pass  # no published posts -> no images

        q.put(json.dumps({"type": "done", "run_id": run_id,
                          "published": len(published),
                          "total": len(final.posts)}))
    except Exception as exc:
        q.put(json.dumps({"type": "error", "message": f"{type(exc).__name__}: {exc}"}))
    finally:
        q.put(None)  # sentinel: tells the SSE generator to close


@api.get("/api/stream/{run_id}")
def stream_run(run_id: str):
    if run_id not in RUNS:
        raise HTTPException(status_code=404, detail="Unknown run_id")
    q: queue.Queue = RUNS[run_id]["queue"]

    def event_source():
        while True:
            item = q.get()
            if item is None:
                break
            yield f"data: {item}\n\n"
        yield 'data: {"type": "closed"}\n\n'

    return StreamingResponse(event_source(), media_type="text/event-stream")


@api.get("/api/image/{run_id}/{name}")
def get_image(run_id: str, name: str):
    # Path(name).name strips any sneaky traversal attempts.
    path = RUNS_DIR / f"react-{run_id}" / "images" / Path(name).name
    if not path.is_file():
        raise HTTPException(status_code=404, detail="Image not found")
    return FileResponse(path)


# Serve the built React app when it exists (after `npm run build`).
_dist = Path(__file__).parent / "frontend" / "dist"
if _dist.is_dir():
    api.mount("/", StaticFiles(directory=_dist, html=True), name="frontend")
else:
    @api.get("/")
    def root():
        return {"status": "API running", "ui": "npm run dev in ./frontend for the React UI"}
