"""グラフ構築(既存網+シナリオオーバーレイ)と Dijkstra。

ノード = 路線ごとの駅(station-on-line)。同一物理駅は gid(駅グループID)で
関連付け、乗換エッジで接続する。エッジコストは分。

エッジ種別:
  ride     : 隣接駅間の乗車。時間は network.json の time_min
  transfer : 乗換(歩行 + 乗換抵抗 + 乗る路線の平均待ち headway/2)。有向で、
             行き先ノードの路線の headway を用いる
"""

from __future__ import annotations

import heapq
import math
from dataclasses import dataclass, field

from .geo import approx_km
from .loader import LineInfo, Network, StationRec
from .params import Params

RIDE = 0
TRANSFER = 1


@dataclass
class TransitGraph:
    node_ids: list[str]
    node_index: dict[str, int]
    lons: list[float]
    lats: list[float]
    names: list[str]
    gids: list  # gid(int)または None
    line_ids: list[str]
    lines: dict[str, LineInfo]
    # adj[u] = list of (v, minutes, kind)
    adj: list[list[tuple[int, float, int]]]
    n_base_nodes: int  # 先頭 n 個が既存網のノード(以降はシナリオの新駅)

    def nodes_within(self, lon: float, lat: float, radius_m: float) -> list[tuple[int, float]]:
        """指定点から radius_m 以内のノードと距離(m)。"""
        out = []
        for i in range(len(self.node_ids)):
            d = approx_km(lon, lat, self.lons[i], self.lats[i]) * 1000.0
            if d <= radius_m:
                out.append((i, d))
        return out

    def headway_of(self, node: int) -> float:
        return self.lines[self.line_ids[node]].headway_min


def _grid_key(lon: float, lat: float) -> tuple[int, int]:
    # 乗換候補探索用の粗いグリッド(約 500m)
    return (int(lat * 200), int(lon * 160))


def build_graph(net: Network, scenario: dict | None = None, params: Params | None = None) -> TransitGraph:
    """既存網(+シナリオの新設路線)から探索グラフを構築する。"""
    params = params or Params()

    stations: list[StationRec] = list(net.stations)
    lines: dict[str, LineInfo] = dict(net.lines)
    links: list[tuple[str, str, str, float]] = [
        (k.from_id, k.to_id, k.line_id, k.time_min) for k in net.links
    ]
    n_base_nodes = len(stations)
    new_station_ids: set[str] = set()

    # --- シナリオの新設路線をオーバーレイ ---
    if scenario:
        gid_by_station = {s.id: s.gid for s in net.stations}
        for li, line in enumerate(scenario.get("lines", [])):
            sts = line.get("stations", [])
            if len(sts) < 2:
                continue
            line_id = f"new_{li}"
            speed = float(line.get("speed_kmh", 35.0))
            headway = float(line.get("headway_min", 6.0))
            lines[line_id] = LineInfo(
                id=line_id, name=line.get("name", f"新線{li + 1}"), category="new",
                color=line.get("color", "#FF3B30"), speed_kmh=speed, headway_min=headway,
            )
            detour = float(net.meta.get("detour_factor", 1.2))
            prev = None
            for si, st in enumerate(sts):
                sid = f"{line_id}_{si}"
                snap = st.get("snap_station_id")
                gid = gid_by_station.get(snap) if snap else None
                stations.append(StationRec(
                    id=sid, gid=gid, name=st.get("name", f"新駅{si + 1}"),
                    line_id=line_id, lon=float(st["lon"]), lat=float(st["lat"]),
                ))
                new_station_ids.add(sid)
                if prev is not None:
                    dist = approx_km(prev.lon, prev.lat, float(st["lon"]), float(st["lat"])) * detour
                    tmin = max(1.0, dist / speed * 60.0)
                    links.append((prev.id, sid, line_id, tmin))
                prev = stations[-1]

    # --- ノード表 ---
    node_ids = [s.id for s in stations]
    node_index = {sid: i for i, sid in enumerate(node_ids)}
    lons = [s.lon for s in stations]
    lats = [s.lat for s in stations]
    names = [s.name for s in stations]
    gids = [s.gid for s in stations]
    line_ids = [s.line_id for s in stations]
    adj: list[list[tuple[int, float, int]]] = [[] for _ in stations]

    # --- 乗車エッジ(双方向) ---
    for from_id, to_id, _line_id, tmin in links:
        u, v = node_index.get(from_id), node_index.get(to_id)
        if u is None or v is None:
            continue
        adj[u].append((v, tmin, RIDE))
        adj[v].append((u, tmin, RIDE))

    # --- 乗換エッジ ---
    def add_transfer(u: int, v: int, walk_min: float) -> None:
        # u→v: v の路線に乗るための待ちを含む(有向)
        adj[u].append((v, walk_min + params.transfer_penalty_min
                       + lines[line_ids[v]].headway_min / 2.0, TRANSFER))
        adj[v].append((u, walk_min + params.transfer_penalty_min
                       + lines[line_ids[u]].headway_min / 2.0, TRANSFER))

    linked: set[tuple[int, int]] = set()

    # 1) 同一駅グループ(gid)同士
    by_gid: dict = {}
    for i, g in enumerate(gids):
        if g is not None:
            by_gid.setdefault(g, []).append(i)
    for group in by_gid.values():
        for a in range(len(group)):
            for b in range(a + 1, len(group)):
                u, v = group[a], group[b]
                if line_ids[u] == line_ids[v]:
                    continue
                linked.add((min(u, v), max(u, v)))
                add_transfer(u, v, params.same_gid_walk_min)

    # 2) 近接駅同士(空間グリッドで近傍探索)
    grid: dict[tuple[int, int], list[int]] = {}
    for i in range(len(node_ids)):
        grid.setdefault(_grid_key(lons[i], lats[i]), []).append(i)

    for i in range(len(node_ids)):
        radius = (params.new_station_transfer_radius_m
                  if node_ids[i] in new_station_ids else params.transfer_radius_m)
        ki, kj = _grid_key(lons[i], lats[i])
        for di in (-1, 0, 1):
            for dj in (-1, 0, 1):
                for j in grid.get((ki + di, kj + dj), ()):
                    if j <= i or line_ids[i] == line_ids[j]:
                        continue
                    key = (i, j)
                    if key in linked:
                        continue
                    r = max(radius, params.new_station_transfer_radius_m
                            if node_ids[j] in new_station_ids else 0.0)
                    d_m = approx_km(lons[i], lats[i], lons[j], lats[j]) * 1000.0
                    if d_m <= r:
                        linked.add(key)
                        add_transfer(i, j, d_m / params.walk_speed_m_min)

    return TransitGraph(
        node_ids=node_ids, node_index=node_index, lons=lons, lats=lats,
        names=names, gids=gids, line_ids=line_ids, lines=lines, adj=adj,
        n_base_nodes=n_base_nodes,
    )


def dijkstra(
    graph: TransitGraph,
    sources: list[tuple[int, float]],
    with_prev: bool = False,
) -> tuple[list[float], list[tuple[int, int] | None] | None]:
    """マルチソース Dijkstra。

    sources: (ノード, 初期コスト) のリスト。
    戻り値: (dist[分], prev)。prev[v] = (直前ノード, エッジ種別) / 出発ノードは None。
    """
    n = len(graph.node_ids)
    dist = [math.inf] * n
    prev: list[tuple[int, int] | None] | None = [None] * n if with_prev else None
    heap: list[tuple[float, int]] = []
    for node, cost in sources:
        if cost < dist[node]:
            dist[node] = cost
            heapq.heappush(heap, (cost, node))
    while heap:
        d, u = heapq.heappop(heap)
        if d > dist[u]:
            continue
        for v, w, kind in graph.adj[u]:
            nd = d + w
            if nd < dist[v] - 1e-9:
                dist[v] = nd
                if prev is not None:
                    prev[v] = (u, kind)
                heapq.heappush(heap, (nd, v))
    return dist, prev
