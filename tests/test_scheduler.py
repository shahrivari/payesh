"""Verify scheduled collection, shared locking, and incremental storage offline."""

import asyncio
import time
import pytest

from fastapi.testclient import TestClient

from payesh import service, web_storage as store
from payesh.database import save_announcements
from payesh.ifb import Announcement, PdfDocument
from payesh.scheduler import CollectionScheduler
from payesh.web import create_app


@pytest.fixture(autouse=True)
def offline_tse(monkeypatch):
    monkeypatch.setattr(service.tse, "fetch_announcements", lambda: [])


def test_automatic_updates_append_without_duplicates(tmp_path, monkeypatch):
    path = tmp_path / "scheduled.sqlite3"
    store.initialize(path)
    save_announcements([Announcement("1", "old", "123", "original", "1405/07/18", "https://ifb.ir/123")], path)
    rows = [Announcement("1", "old", "123", "updated", "1405/07/18", "https://ifb.ir/123"),
            Announcement("2", "new", "124", "new record", "1405/07/19", "https://ifb.ir/124")]
    monkeypatch.setattr(service, "fetch_announcements", lambda: rows)
    monkeypatch.setattr(service, "download_announcement_pdf", lambda url: PdfDocument("file.pdf", b"%PDF-fixture", "application/pdf"))
    with TestClient(create_app(path, update_interval=0.03)) as client:
        deadline = time.monotonic() + 3
        while time.monotonic() < deadline:
            runs = client.get("/api/v1/collection-runs").json()["items"]
            if sum(run["status"] == "completed" for run in runs) >= 2:
                break
            time.sleep(0.01)
        else:
            raise AssertionError("Automatic collector did not complete twice")
        assert all(run["started_by"] == "scheduled" for run in runs)
        assert client.get("/api/v1/announcements").json()["total"] == 2
        assert client.get("/api/v1/announcements/123").json()["title"] == "updated"
        assert client.get("/api/v1/stats").json()["auto_update"]["enabled"] is True
        assert client.get("/api/v1/stats").json()["auto_update"]["next_run_at"] is not None


def test_scheduled_tick_skips_active_manual_run(tmp_path):
    path = tmp_path / "busy.sqlite3"
    store.initialize(path)
    manual = store.start_run(path)
    executed = []
    scheduler = CollectionScheduler(path, executed.append)
    asyncio.run(scheduler.run_once())
    assert executed == []
    assert store.recent_runs(path)[0]["id"] == manual
    assert store.recent_runs(path)[0]["started_by"] == "manual"


def test_hourly_default_and_disabled_mode(tmp_path):
    with TestClient(create_app(tmp_path / "hourly.sqlite3")) as client:
        schedule = client.get("/api/v1/stats").json()["auto_update"]
        assert schedule["interval_seconds"] == 3600
        assert schedule["enabled"] is True
        assert client.get("/api/v1/collection-runs").json()["items"] == []
    with TestClient(create_app(tmp_path / "disabled.sqlite3", update_interval=0)) as client:
        schedule = client.get("/api/v1/stats").json()["auto_update"]
        assert schedule["enabled"] is False
        assert schedule["next_run_at"] is None
