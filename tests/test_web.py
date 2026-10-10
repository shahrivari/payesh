"""Exercise the API against real temporary SQLite storage and offline sources."""

import json
from bs4 import BeautifulSoup

from fastapi.testclient import TestClient
import pytest

from payesh import service, web_storage as store
from payesh.database import save_announcement_file, save_announcements
from payesh.extraction import extract_target_pdfs
from payesh.ifb import Announcement, PdfDocument
from payesh.web import create_app


@pytest.fixture
def database(tmp_path):
    path = tmp_path / "payesh.sqlite3"
    store.initialize(path)
    save_announcements([
        Announcement("1", "اراد155", "123", "سود روزشمار", "۱۴۰۵/۷/۱۸", "https://ifb.ir/123"),
        Announcement("2", "صبا", "124", "پذیره نویسی", "1405/07/17", "https://ifb.ir/124"),
        Announcement("3", "اخزا", "125", "اسناد خزانه", "1405/06/30", "https://ifb.ir/125"),
    ], path)
    save_announcement_file("123", "گزارش.pdf", b"%PDF-1.4\nfixture", db_path=path)
    with store.connection(path) as db:
        data = {"symbol": "اراد155", "nominal_value_rial": "999999999999999999999", "annual_yield_percent": "23"}
        db.execute("INSERT INTO announcement_extractions VALUES (?, ?, ?, ?, ?)",
                   ("123", "daily_interest", "complete", json.dumps(data), store.now()))
        db.execute("INSERT INTO daily_interest_values VALUES (?, ?, ?)", ("123", "1405/07/18", "999999999999999999999"))
    return path


@pytest.fixture
def client(database):
    with TestClient(create_app(database)) as client:
        yield client


def test_list_pagination_and_normalized_search(client):
    first = client.get("/api/v1/announcements", params={"page_size": 1}).json()
    assert first["total"] == 3
    assert first["items"][0]["notice_number"] == "123"
    assert "file_blob" not in first["items"][0]
    second = client.get("/api/v1/announcements", params={"page_size": 1, "page": 2}).json()
    assert second["items"][0]["notice_number"] == "124"
    searched = client.get("/api/v1/announcements", params={"q": "اراد۱۵۵"}).json()
    assert searched["total"] == 1


def test_filters_and_source_calendar_dates(client):
    response = client.get("/api/v1/announcements", params={"date_from": "۱۴۰۵/۰۷/۱۸", "date_to": "1405-07-18", "status": "complete", "document_type": "daily_interest", "symbol": "اراد۱۵۵"})
    assert response.status_code == 200
    assert response.json()["total"] == 1
    assert client.get("/api/v1/announcements", params={"status": "none"}).json()["total"] == 2


@pytest.mark.parametrize("params", [{"page": 0}, {"page_size": 101}, {"status": "invalid"}, {"date_from": "bad"}, {"date_to": "1405-13-01"}, {"date_from": "1405-07-20", "date_to": "1405-07-01"}])
def test_invalid_query_parameters(client, params):
    assert client.get("/api/v1/announcements", params=params).status_code == 422


def test_detail_preserves_monetary_precision(client):
    detail = client.get("/api/v1/announcements/123").json()
    assert detail["extracted_data"]["nominal_value_rial"] == "999999999999999999999"
    assert detail["daily_interest_values"][0]["amount_rial"] == "999999999999999999999"
    assert detail["has_pdf"] == 1
    assert client.get("/api/v1/announcements/missing").status_code == 404


def test_pdf_download_and_missing_file(client):
    response = client.get("/api/v1/announcements/123/pdf")
    assert response.content.startswith(b"%PDF-")
    assert response.headers["content-type"] == "application/pdf"
    assert response.headers["content-disposition"].startswith("inline;")
    assert "filename*=UTF-8''" in response.headers["content-disposition"]
    assert client.get("/api/v1/announcements/123/pdf?download=true").headers["content-disposition"].startswith("attachment;")
    assert client.get("/api/v1/announcements/124/pdf").status_code == 404


def test_notice_numbers_with_slashes(client, database):
    save_announcements([Announcement("4", "آزمایش", "05/و/11684", "عنوان", "1405/07/19", "https://ifb.ir/fixture")], database)
    save_announcement_file("05/و/11684", "file.pdf", b"%PDF-fixture", db_path=database)
    assert client.get("/api/v1/announcements/05%2F%D9%88%2F11684").json()["notice_number"] == "05/و/11684"
    assert client.get("/api/v1/announcements/05%2F%D9%88%2F11684/pdf").content == b"%PDF-fixture"


def test_dashboard_stats_and_empty_startup(client, tmp_path):
    assert client.get("/").status_code == 200
    assert client.get("/static/app.js").status_code == 200
    stats = client.get("/api/v1/stats").json()
    assert (stats["announcement_count"], stats["pdf_count"], stats["complete_count"]) == (3, 1, 1)
    with TestClient(create_app(tmp_path / "empty.sqlite3")) as empty:
        assert empty.get("/api/v1/announcements").json()["items"] == []
        assert empty.get("/api/v1/stats").json()["announcement_count"] == 0


def test_dashboard_controls_have_unique_ids(client):
    page = BeautifulSoup(client.get("/").text, "html.parser")
    ids = [element["id"] for element in page.find_all(id=True)]
    assert len(ids) == len(set(ids))
    assert page.find(id="search").name == "input"


def test_collection_result_and_failure_history(client, monkeypatch):
    monkeypatch.setattr(service, "fetch_announcements", lambda: [])
    monkeypatch.setattr(service, "download_announcement_pdf", lambda url: PdfDocument("download.pdf", b"%PDF-1.4\nfixture", "application/pdf"))
    response = client.post("/api/v1/collection-runs")
    assert response.status_code == 202
    run = client.get("/api/v1/collection-runs/" + response.json()["id"]).json()
    assert run["status"] == "completed"
    assert run["result"]["downloaded"] == 2
    assert "announcements" not in run["result"]
    def fail():
        raise RuntimeError("offline fixture failure")
    monkeypatch.setattr(service, "fetch_announcements", fail)
    response = client.post("/api/v1/collection-runs")
    failed = client.get("/api/v1/collection-runs/" + response.json()["id"]).json()
    assert failed["status"] == "failed"
    assert "offline fixture failure" in failed["error"]
    assert len(client.get("/api/v1/collection-runs").json()["items"]) == 2


def test_partial_collection_is_reported(client, monkeypatch):
    monkeypatch.setattr(service, "fetch_announcements", lambda: [])
    def fail(url):
        raise RuntimeError("download failure")
    monkeypatch.setattr(service, "download_announcement_pdf", fail)
    response = client.post("/api/v1/collection-runs")
    run = client.get("/api/v1/collection-runs/" + response.json()["id"]).json()
    assert run["status"] == "partial"
    assert len(run["result"]["failures"]) == 2


def test_overlap_restart_and_cross_origin(client, database):
    run_id = store.start_run(database)
    assert store.start_run(database) is None
    assert client.post("/api/v1/collection-runs").status_code == 409
    assert client.post("/api/v1/collection-runs", headers={"origin": "https://other.example"}).status_code == 403
    assert client.post("/api/v1/collection-runs", headers={"sec-fetch-site": "cross-site"}).status_code == 403
    store.initialize(database)
    assert store.get_run(database, run_id)["status"] == "interrupted"
    assert store.start_run(database) is not None
    assert client.get("/api/v1/collection-runs/missing").status_code == 404


def test_extraction_error_removes_stale_daily_values(database):
    save_announcement_file("123", "brokenN.pdf", b"%PDF-1.4\nbroken", db_path=database)
    assert extract_target_pdfs(database) == (1, 0, 1, 0)
    result = store.detail(database, "123")
    assert result["extraction_status"] == "error"
    assert result["daily_interest_values"] == []
