"""API の結合テスト(実データ使用)。"""

import os
import tempfile

import pytest
from fastapi.testclient import TestClient

os.environ["TRANSIM_DB"] = os.path.join(tempfile.mkdtemp(), "test_scenarios.db")

from app.main import app  # noqa: E402

client = TestClient(app)


def test_config():
    r = client.get("/api/config")
    assert r.status_code == 200
    body = r.json()
    assert body["area"] == "keihanshin"
    assert len(body["breaks_min_default"]) == 4


def test_network_geojson():
    r = client.get("/api/network/geojson")
    assert r.status_code == 200
    body = r.json()
    assert len(body["lines"]["features"]) > 100
    assert len(body["stations"]["features"]) > 1500


def test_scenario_crud_and_analysis():
    # 作成
    r = client.post("/api/scenarios", json={"name": "テスト案"})
    assert r.status_code == 201
    sid = r.json()["id"]

    # 更新(なにわ筋線風の新線: 大阪駅そば→中之島→難波そば)
    lines = [{
        "name": "なにわ筋線風", "color": "#FF3B30", "speed_kmh": 40.0, "headway_min": 6.0,
        "stations": [
            {"name": "うめきた", "lon": 135.4945, "lat": 34.7040, "snap_station_id": None},
            {"name": "中之島", "lon": 135.4900, "lat": 34.6900, "snap_station_id": None},
            {"name": "西本町", "lon": 135.4930, "lat": 34.6800, "snap_station_id": None},
            {"name": "難波新駅", "lon": 135.4980, "lat": 34.6650, "snap_station_id": None},
        ],
    }]
    r = client.put(f"/api/scenarios/{sid}", json={"lines": lines})
    assert r.status_code == 200
    assert r.json()["lines"][0]["name"] == "なにわ筋線風"

    # 一覧・複製
    assert any(s["id"] == sid for s in client.get("/api/scenarios").json())
    r = client.post(f"/api/scenarios/{sid}/duplicate")
    assert r.status_code == 201
    dup_id = r.json()["id"]

    # 等時圏(中之島起点: 新線で改善するはず)
    r = client.post("/api/analysis/isochrone",
                    json={"origin": [135.4900, 34.6900], "scenario_id": sid})
    assert r.status_code == 200
    body = r.json()
    assert body["after"] is not None
    last = body["summary"][-1]
    assert last["area_km2_after"] >= last["area_km2_before"]

    # 経路(うめきた→難波)
    r = client.post("/api/analysis/route",
                    json={"origin": [135.4945, 34.7040],
                          "destination": [135.4980, 34.6650], "scenario_id": sid})
    assert r.status_code == 200
    body = r.json()
    assert body["before"]["total_min"] > 0
    assert body["after"]["total_min"] <= body["before"]["total_min"] + 0.1

    # 削除
    assert client.delete(f"/api/scenarios/{sid}").status_code == 204
    assert client.delete(f"/api/scenarios/{dup_id}").status_code == 204
    assert client.get(f"/api/scenarios/{sid}").status_code == 404


def test_isochrone_without_scenario():
    r = client.post("/api/analysis/isochrone", json={"origin": [135.4959, 34.7024]})
    assert r.status_code == 200
    body = r.json()
    assert body["after"] is None
    assert len(body["before"]["features"]) >= 3


def test_route_unreachable():
    # 海上(駅から遠い)同士
    r = client.post("/api/analysis/route",
                    json={"origin": [135.0, 34.3], "destination": [135.05, 34.32]})
    assert r.status_code in (200, 422)
