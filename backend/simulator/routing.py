"""2地点間の最短経路(徒歩アクセス+公共交通)とレグ分解。"""

from __future__ import annotations

import math

from .geo import approx_km
from .graph import RIDE, TransitGraph, dijkstra
from .params import Params


def shortest_route(
    graph: TransitGraph,
    origin: tuple[float, float],
    destination: tuple[float, float],
    params: Params,
) -> dict | None:
    """経路を計算し {"total_min", "legs"} を返す。到達不能なら None。

    legs: [{type: walk|ride|transfer, line_name, line_color, from_name, to_name,
            minutes, coords}]
    """
    o_lon, o_lat = origin
    d_lon, d_lat = destination

    # 出発地→駅(初乗り待ち込み)。徒歩分は別記録してレグ化する
    access = graph.nodes_within(o_lon, o_lat, params.access_radius_m)
    sources = []
    access_walk: dict[int, float] = {}
    for node, d_m in access:
        walk = d_m / params.walk_speed_m_min
        access_walk[node] = walk
        sources.append((node, walk + graph.headway_of(node) / 2.0))

    egress = {
        node: d_m / params.walk_speed_m_min
        for node, d_m in graph.nodes_within(d_lon, d_lat, params.access_radius_m)
    }

    # 徒歩直行(近距離用フォールバック)
    walk_direct_min = (
        approx_km(o_lon, o_lat, d_lon, d_lat) * 1000.0
        * params.direct_walk_detour / params.walk_speed_m_min
    )

    best_node, best_total = None, math.inf
    if sources and egress:
        dist, prev = dijkstra(graph, sources, with_prev=True)
        for node, walk in egress.items():
            total = dist[node] + walk
            if total < best_total:
                best_total, best_node = total, node

    if walk_direct_min <= best_total and walk_direct_min <= 90.0:
        return {
            "total_min": round(walk_direct_min, 1),
            "legs": [{
                "type": "walk", "line_name": None, "line_color": None,
                "from_name": "出発地", "to_name": "目的地",
                "minutes": round(walk_direct_min, 1),
                "coords": [[o_lon, o_lat], [d_lon, d_lat]],
            }],
        }
    if best_node is None or not math.isfinite(best_total):
        return None

    # --- 経路復元 ---
    path: list[int] = [best_node]
    kinds: list[int] = []  # kinds[k] = path[k] → path[k+1] のエッジ種別(逆順構築後に反転)
    node = best_node
    while prev[node] is not None:
        p, kind = prev[node]
        path.append(p)
        kinds.append(kind)
        node = p
    path.reverse()
    kinds.reverse()
    first = path[0]

    legs: list[dict] = []
    # 出発徒歩
    legs.append({
        "type": "walk", "line_name": None, "line_color": None,
        "from_name": "出発地", "to_name": graph.names[first],
        "minutes": round(access_walk.get(first, 0.0), 1),
        "coords": [[o_lon, o_lat], [graph.lons[first], graph.lats[first]]],
    })
    # 初乗り待ちは最初の乗車レグに計上する
    pending_wait = graph.headway_of(first) / 2.0

    k = 0
    while k < len(kinds):
        u = path[k]
        if kinds[k] == RIDE:
            # 同一路線の連続乗車をまとめる
            line_id = graph.line_ids[u]
            j = k
            minutes = 0.0
            coords = [[graph.lons[u], graph.lats[u]]]
            while j < len(kinds) and kinds[j] == RIDE and graph.line_ids[path[j]] == line_id:
                w = _edge_weight(graph, path[j], path[j + 1], RIDE)
                minutes += w
                coords.append([graph.lons[path[j + 1]], graph.lats[path[j + 1]]])
                j += 1
            line = graph.lines[line_id]
            legs.append({
                "type": "ride", "line_name": line.name, "line_color": line.color,
                "from_name": graph.names[u], "to_name": graph.names[path[j]],
                "minutes": round(minutes + pending_wait, 1),
                "coords": coords,
            })
            pending_wait = 0.0
            k = j
        else:
            v = path[k + 1]
            w = _edge_weight(graph, u, v, kinds[k])
            line = graph.lines[graph.line_ids[v]]
            legs.append({
                "type": "transfer", "line_name": line.name, "line_color": line.color,
                "from_name": graph.names[u], "to_name": graph.names[v],
                "minutes": round(w + pending_wait, 1),
                "coords": [[graph.lons[u], graph.lats[u]], [graph.lons[v], graph.lats[v]]],
            })
            pending_wait = 0.0
            k += 1

    # 到着徒歩
    last = path[-1]
    legs.append({
        "type": "walk", "line_name": None, "line_color": None,
        "from_name": graph.names[last], "to_name": "目的地",
        "minutes": round(egress[last], 1),
        "coords": [[graph.lons[last], graph.lats[last]], [d_lon, d_lat]],
    })

    return {"total_min": round(best_total, 1), "legs": legs}


def _edge_weight(graph: TransitGraph, u: int, v: int, kind: int) -> float:
    for to, w, k in graph.adj[u]:
        if to == v and k == kind:
            return w
    raise ValueError(f"edge not found: {u}->{v} kind={kind}")
