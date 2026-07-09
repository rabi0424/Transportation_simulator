"""計算エンジンのユニットテスト(人工ネットワーク+実データのサニティ)。"""

import math
from pathlib import Path

import pytest

from simulator import Params, build_graph, compute_isochrone, load_network, shortest_route
from simulator.geo import cell_from_meshcode, cell_of, meshcode_500m
from simulator.graph import dijkstra
from simulator.loader import LineInfo, LinkRec, Network, StationRec

DATA = Path(__file__).resolve().parents[2] / "data" / "keihanshin" / "network.json"

# 東西に一直線の路線A(3駅、駅間4分)と、中央駅で交差する路線B(2駅、5分)。
# A2 と B1 は同一駅グループ (gid=100)。座標は約0.9km間隔。
def tiny_network() -> Network:
    lines = {
        "A": LineInfo("A", "路線A", "private", "#111111", 40.0, 6.0),
        "B": LineInfo("B", "路線B", "metro", "#222222", 30.0, 4.0),
    }
    stations = [
        StationRec("A_1", 1, "西駅", "A", 135.00, 34.70),
        StationRec("A_2", 100, "中央", "A", 135.01, 34.70),
        StationRec("A_3", 3, "東駅", "A", 135.02, 34.70),
        StationRec("B_1", 100, "中央", "B", 135.01, 34.70),
        StationRec("B_2", 5, "北駅", "B", 135.01, 34.71),
    ]
    links = [
        LinkRec("A_1", "A_2", "A", 0.9, 4.0),
        LinkRec("A_2", "A_3", "A", 0.9, 4.0),
        LinkRec("B_1", "B_2", "B", 1.1, 5.0),
    ]
    return Network(meta={"bbox": [134.9, 34.6, 135.1, 34.8]}, lines=lines,
                   stations=stations, links=links)


def test_ride_edge_shortest_path():
    g = build_graph(tiny_network())
    src = g.node_index["A_1"]
    dist, _ = dijkstra(g, [(src, 0.0)])
    assert dist[g.node_index["A_3"]] == pytest.approx(8.0)


def test_transfer_via_gid():
    p = Params()
    g = build_graph(tiny_network(), params=p)
    src = g.node_index["A_1"]
    dist, _ = dijkstra(g, [(src, 0.0)])
    # A_1→A_2(4分) + 乗換(歩2+抵抗3+待ち2) + B_1→B_2(5分)
    expected = 4.0 + (p.same_gid_walk_min + p.transfer_penalty_min + 4.0 / 2) + 5.0
    assert dist[g.node_index["B_2"]] == pytest.approx(expected)


def test_scenario_overlay_adds_line_and_improves_time():
    net = tiny_network()
    scenario = {"lines": [{
        "name": "新線", "speed_kmh": 60.0, "headway_min": 5.0,
        "stations": [
            {"name": "西駅", "lon": 135.00, "lat": 34.70, "snap_station_id": "A_1"},
            {"name": "北駅", "lon": 135.01, "lat": 34.71, "snap_station_id": "B_2"},
        ],
    }]}
    p = Params()
    g0 = build_graph(net, params=p)
    g1 = build_graph(net, scenario, params=p)
    assert len(g1.node_ids) == len(g0.node_ids) + 2

    # 西駅そば → 北駅そば の所要時間がシナリオで短縮される
    origin, dest = (135.0005, 34.7005), (135.0105, 34.7105)
    r0 = shortest_route(g0, origin, dest, p)
    r1 = shortest_route(g1, origin, dest, p)
    assert r1["total_min"] < r0["total_min"]


def test_route_legs_consistency():
    p = Params()
    g = build_graph(tiny_network(), params=p)
    r = shortest_route(g, (135.0005, 34.7005), (135.0105, 34.7105), p)
    assert r["legs"][0]["type"] == "walk"
    assert r["legs"][-1]["type"] == "walk"
    total_legs = sum(leg["minutes"] for leg in r["legs"])
    assert total_legs == pytest.approx(r["total_min"], abs=0.5)


def test_isochrone_bands_monotonic():
    net = tiny_network()
    p = Params(breaks_min=(10.0, 20.0, 30.0))
    g = build_graph(net, params=p)
    iso = compute_isochrone(net, g, (135.0005, 34.7005), p)
    areas = [s["area_km2"] for s in iso["summary"]]
    assert areas == sorted(areas)
    assert areas[0] > 0
    stations = [s["stations"] for s in iso["summary"]]
    assert stations == sorted(stations)
    for f in iso["bands"]["features"]:
        assert f["geometry"]["type"] in ("Polygon", "MultiPolygon")


def test_meshcode_roundtrip():
    for lat, lon in [(34.7024, 135.4959), (35.0116, 135.7681), (34.4320, 135.2430)]:
        code = meshcode_500m(lat, lon)
        assert len(code) == 9
        assert cell_from_meshcode(code) == cell_of(lon, lat)


# --- 実データ(京阪神)のサニティテスト ---

@pytest.fixture(scope="module")
def keihanshin():
    net = load_network(DATA)
    return net, build_graph(net)


def test_real_network_size(keihanshin):
    net, g = keihanshin
    assert len(g.node_ids) > 1500
    assert sum(len(a) for a in g.adj) > 3000


def test_real_osaka_to_kyoto(keihanshin):
    net, g = keihanshin
    r = shortest_route(g, (135.4959, 34.7024), (135.7585, 34.9858), Params())
    # 実際の新快速+アクセスで 35分前後。単一表定速度の近似なので 30〜75分なら妥当
    assert 30.0 <= r["total_min"] <= 75.0
    ride_lines = [l["line_name"] for l in r["legs"] if l["type"] == "ride"]
    assert any("京都線" in n for n in ride_lines)


def test_real_isochrone_from_umeda(keihanshin):
    net, g = keihanshin
    iso = compute_isochrone(net, g, (135.4959, 34.7024), Params())
    summary = iso["summary"]
    # 60分圏は 300km2 以上、駅数は 300 以上に達するはず
    assert summary[-1]["area_km2"] > 300
    assert summary[-1]["stations"] > 300


def test_real_scenario_isochrone_improves(keihanshin):
    net, _ = keihanshin
    p = Params()
    # 此花区・夢洲方面へ地下鉄中央線コスモスクエアから延伸する架空新線
    scenario = {"lines": [{
        "name": "夢洲新線", "speed_kmh": 35.0, "headway_min": 6.0,
        "stations": [
            {"name": "コスモスクエア", "lon": 135.4189, "lat": 34.6424,
             "snap_station_id": None},
            {"name": "夢洲", "lon": 135.4020, "lat": 34.6660, "snap_station_id": None},
            {"name": "新桜島", "lon": 135.4230, "lat": 34.6800, "snap_station_id": None},
        ],
    }]}
    g0 = build_graph(net, params=p)
    g1 = build_graph(net, scenario, params=p)
    origin = (135.4020, 34.6660)  # 夢洲
    iso0 = compute_isochrone(net, g0, origin, p)
    iso1 = compute_isochrone(net, g1, origin, p)
    a0 = iso0["summary"][-1]["area_km2"]
    a1 = iso1["summary"][-1]["area_km2"]
    assert a1 > a0
