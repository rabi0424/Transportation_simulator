"""等時圏計算。

駅までの徒歩アクセス → 乗換込み Dijkstra → 駅からの徒歩で 500m メッシュを
被覆し、時間帯(バンド)ごとのポリゴンと集計(面積・人口・到達駅数)を返す。
"""

from __future__ import annotations

import math

from shapely.geometry import box, mapping
from shapely.ops import unary_union

from .geo import approx_km, cell_area_km2, cell_bounds, cell_center, cell_of
from .graph import TransitGraph, dijkstra
from .loader import Network
from .params import Params


def station_times(graph: TransitGraph, origin: tuple[float, float], params: Params) -> list[float]:
    """出発地点から各駅ノードへの所要時間(分)。徒歩アクセス+初乗り待ちを含む。"""
    lon, lat = origin
    sources = []
    for node, d_m in graph.nodes_within(lon, lat, params.access_radius_m):
        cost = d_m / params.walk_speed_m_min + graph.headway_of(node) / 2.0
        sources.append((node, cost))
    dist, _ = dijkstra(graph, sources)
    return dist


def _coverage_cells(
    graph: TransitGraph,
    origin: tuple[float, float],
    dist: list[float],
    params: Params,
) -> dict[tuple[int, int], float]:
    """セル (i,j) → 最小到達時間(分)。"""
    lon0, lat0 = origin
    max_min = params.breaks_min[-1]
    walk_km_min = params.walk_speed_m_min / 1000.0
    cells: dict[tuple[int, int], float] = {}

    def stamp(lon: float, lat: float, t0: float, walk_cap_min: float) -> None:
        budget = min(max_min - t0, walk_cap_min)
        if budget <= 0:
            return
        radius_km = budget * walk_km_min
        dlat = radius_km / 111.32
        dlon = radius_km / (111.32 * math.cos(math.radians(lat)))
        i0, j0 = cell_of(lon, lat - dlat)[0], cell_of(lon - dlon, lat)[1]
        i1, j1 = cell_of(lon, lat + dlat)[0], cell_of(lon + dlon, lat)[1]
        for i in range(i0, i1 + 1):
            for j in range(j0, j1 + 1):
                clon, clat = cell_center(i, j)
                d_km = approx_km(lon, lat, clon, clat)
                t = t0 + d_km / walk_km_min
                key = (i, j)
                if t <= max_min and t < cells.get(key, math.inf):
                    cells[key] = t

    # 出発地からの直接徒歩
    stamp(lon0, lat0, 0.0, params.egress_walk_cap_min + 5.0)
    # 各駅からの徒歩
    for node, t in enumerate(dist):
        if t < max_min:
            stamp(graph.lons[node], graph.lats[node], t, params.egress_walk_cap_min)
    return cells


def compute_isochrone(
    net: Network,
    graph: TransitGraph,
    origin: tuple[float, float],
    params: Params,
) -> dict:
    """バンド(非重複リング)GeoJSON と累積サマリーを返す。

    戻り値: {"bands": [Feature...], "summary": [{max_min, area_km2, population|None,
              stations} ...]}  (summary は累積値)
    """
    breaks = list(params.breaks_min)
    dist = station_times(graph, origin, params)
    cells = _coverage_cells(graph, origin, dist, params)

    # バンド割当(cells は非重複なのでバンドも非重複)
    band_cells: list[list[tuple[int, int]]] = [[] for _ in breaks]
    for cell, t in cells.items():
        for bi, b in enumerate(breaks):
            if t <= b:
                band_cells[bi].append(cell)
                break

    features = []
    cum_area = 0.0
    cum_pop = 0.0
    summary = []
    prev_break = 0.0
    for bi, b in enumerate(breaks):
        geoms = [box(*cell_bounds(i, j)) for (i, j) in band_cells[bi]]
        merged = unary_union(geoms) if geoms else None
        if merged is not None and not merged.is_empty:
            merged = merged.simplify(0.0001)
            features.append({
                "type": "Feature",
                "geometry": mapping(merged),
                "properties": {"min_min": prev_break, "max_min": b},
            })
        cum_area += sum(cell_area_km2(i, j) for (i, j) in band_cells[bi])
        if net.population:
            cum_pop += sum(net.population.get(c, 0.0) for c in band_cells[bi])
        n_stations = len({
            (graph.gids[n] if graph.gids[n] is not None else graph.node_ids[n])
            for n, t in enumerate(dist) if t <= b
        })
        summary.append({
            "max_min": b,
            "area_km2": round(cum_area, 1),
            "population": int(round(cum_pop)) if net.population else None,
            "stations": n_stations,
        })
        prev_break = b

    return {
        "bands": {"type": "FeatureCollection", "features": features},
        "summary": summary,
    }
