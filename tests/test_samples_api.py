from pathlib import Path

import pytest

from src.api.rest import server


@pytest.fixture()
def client_with_project(tmp_path, monkeypatch):
    monkeypatch.setattr(server, "PROJECT_ROOT", tmp_path)
    return server.app.test_client(), tmp_path


def test_get_samples_returns_filtered_sorted_items(client_with_project):
    client, project_root = client_with_project
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)

    (data_dir / "b.xlsx").write_bytes(b"b")
    (data_dir / "A.xlsx").write_bytes(b"a")
    (data_dir / "~$temp.xlsx").write_bytes(b"temp")
    (data_dir / "note.csv").write_text("x", encoding="utf-8")

    resp = client.get("/api/samples")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True

    items = body["data"]
    assert [item["name"] for item in items] == ["A.xlsx", "b.xlsx"]
    assert items[0]["path"] == "data/A.xlsx"
    assert items[0]["is_default"] is True
    assert items[1]["is_default"] is False
    assert all(item["size"] > 0 for item in items)
    assert all(item["updated_at"] for item in items)


def test_get_samples_returns_empty_when_no_xlsx(client_with_project):
    client, project_root = client_with_project
    data_dir = project_root / "data"
    data_dir.mkdir(parents=True, exist_ok=True)
    (data_dir / "readme.txt").write_text("demo", encoding="utf-8")

    resp = client.get("/api/samples")
    assert resp.status_code == 200
    body = resp.get_json()
    assert body["success"] is True
    assert body["data"] == []
