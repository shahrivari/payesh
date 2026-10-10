"""Local REST API and Persian web dashboard."""

import argparse
import asyncio
from contextlib import asynccontextmanager
from pathlib import Path
from typing import Literal
from urllib.parse import quote, urlsplit

from fastapi import BackgroundTasks, FastAPI, HTTPException, Query, Request
from fastapi.responses import FileResponse, Response
from fastapi.staticfiles import StaticFiles
import uvicorn

from payesh.database import DEFAULT_DB_PATH
from payesh.service import collect
from payesh.scheduler import CollectionScheduler
from payesh import web_storage as store

STATIC = Path(__file__).parent / "static"


def create_app(db_path: str | Path = DEFAULT_DB_PATH, *, update_interval: float = 3600) -> FastAPI:
    path = Path(db_path).expanduser().resolve()

    @asynccontextmanager
    async def lifespan(app):
        store.initialize(path)
        task = asyncio.create_task(scheduler.run())
        try:
            yield
        finally:
            scheduler.stop.set()
            await task

    app = FastAPI(title="Payesh API", version="0.1.0", lifespan=lifespan)
    app.mount("/static", StaticFiles(directory=STATIC), name="static")

    @app.get("/", include_in_schema=False)
    def home():
        return FileResponse(STATIC / "index.html")

    @app.get("/api/v1/announcements")
    def list_announcements(
        page: int = Query(1, ge=1), page_size: int = Query(20, ge=1, le=100),
        q: str = Query("", max_length=200), symbol: str = Query("", max_length=100),
        status: Literal["", "complete", "partial", "unrecognized", "no_text", "error", "none"] = "",
        document_type: Literal["", "subscription", "daily_interest", "unknown"] = "",
        date_from: str = "", date_to: str = "",
    ):
        dates = []
        for value in (date_from, date_to):
            normalized = store.normalize(value)
            key = store.date_key(value)
            if value and (not key or normalized.replace("/", "-") != key or
                          not 1 <= int(key[5:7]) <= 12 or not 1 <= int(key[8:10]) <= 31):
                raise HTTPException(422, "Dates must use YYYY-MM-DD in the source calendar.")
            dates.append(key)
        if dates[0] and dates[1] and dates[0] > dates[1]:
            raise HTTPException(422, "date_from must be on or before date_to.")
        return store.announcements(path, page=page, page_size=page_size, q=q, symbol=symbol,
                                   status=status, document_type=document_type,
                                   date_from=dates[0], date_to=dates[1])

    @app.get("/api/v1/announcements/{notice_number:path}/pdf")
    def announcement_pdf(notice_number: str, download: bool = False):
        file = store.pdf(path, notice_number)
        if file is None:
            raise HTTPException(404, "Stored PDF not found.")
        filename, content = file
        name = Path(filename.replace("\\", "/")).name
        return Response(content, media_type="application/pdf", headers={
            "Content-Disposition": f"{'attachment' if download else 'inline'}; filename*=UTF-8''{quote(name, safe='')}",
            "X-Content-Type-Options": "nosniff",
        })

    @app.get("/api/v1/announcements/{notice_number:path}")
    def announcement_detail(notice_number: str):
        result = store.detail(path, notice_number)
        if result is None:
            raise HTTPException(404, "Announcement not found.")
        return result

    @app.get("/api/v1/stats")
    def statistics():
        result = store.stats(path)
        result["auto_update"] = scheduler.status()
        return result

    @app.get("/api/v1/collection-runs")
    def runs():
        return {"items": store.recent_runs(path)}

    @app.get("/api/v1/collection-runs/{run_id}")
    def run_status(run_id: str):
        result = store.get_run(path, run_id)
        if result is None:
            raise HTTPException(404, "Collection run not found.")
        return result

    def execute(run_id: str):
        try:
            result = collect(path, progress=lambda stage, done, total: store.progress(path, run_id, stage, done, total))
            result.pop("announcements")
            store.finish(path, run_id, result=result)
        except Exception as exc:
            store.finish(path, run_id, error=str(exc))

    scheduler = CollectionScheduler(path, execute, update_interval)

    @app.post("/api/v1/collection-runs", status_code=202)
    def collect_now(request: Request, tasks: BackgroundTasks):
        origin = request.headers.get("origin")
        if origin and urlsplit(origin).netloc != request.headers.get("host"):
            raise HTTPException(403, "Collection must be started from this application.")
        if request.headers.get("sec-fetch-site") == "cross-site":
            raise HTTPException(403, "Cross-site collection requests are not allowed.")
        run_id = store.start_run(path)
        if run_id is None:
            raise HTTPException(409, "A collection is already running.")
        tasks.add_task(execute, run_id)
        return store.get_run(path, run_id)

    return app


def main():
    parser = argparse.ArgumentParser(description="Start the local Payesh dashboard.")
    parser.add_argument("--db", type=Path, default=DEFAULT_DB_PATH)
    parser.add_argument("--port", type=int, default=8000)
    parser.add_argument("--no-auto-update", action="store_true", help="Disable hourly background collection.")
    args = parser.parse_args()
    uvicorn.run(create_app(args.db, update_interval=0 if args.no_auto_update else 3600), host="127.0.0.1", port=args.port)


if __name__ == "__main__":
    main()
