"""新設路線シミュレーター API (Phase 1)。

起動:  cd backend && uvicorn app.main:app --reload --port 8000
"""

from __future__ import annotations

from fastapi import FastAPI, HTTPException
from fastapi.middleware.cors import CORSMiddleware

from simulator import Params, compute_isochrone, shortest_route

from . import db
from .schemas import IsochroneRequest, RouteRequest, ScenarioCreate, ScenarioUpdate
from .state import get_base_graph, get_network, get_scenario_graph

app = FastAPI(title="Transportation Simulator API", version="0.1.0")

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["*"],
    allow_headers=["*"],
)


@app.get("/api/config")
def config():
    net = get_network()
    bbox = net.bbox
    return {
        "area": net.meta.get("area", "keihanshin"),
        "map_center": [135.50, 34.70],
        "map_zoom": 10,
        "bbox": bbox,
        "breaks_min_default": list(Params().breaks_min),
        "population_available": bool(net.population),
        "source_note": net.meta.get("source", ""),
    }


@app.get("/api/network/geojson")
def network_geojson():
    net = get_network()
    coords_of = {s.id: (s.lon, s.lat) for s in net.stations}

    segments_by_line: dict[str, list] = {}
    for link in net.links:
        if link.dist_km <= 0:
            continue  # 直通リンクは幾何を持たない
        a, b = coords_of.get(link.from_id), coords_of.get(link.to_id)
        if a and b:
            segments_by_line.setdefault(link.line_id, []).append([list(a), list(b)])

    line_features = []
    for line in net.lines.values():
        segs = segments_by_line.get(line.id)
        if not segs:
            continue
        line_features.append({
            "type": "Feature",
            "geometry": {"type": "MultiLineString", "coordinates": segs},
            "properties": {
                "id": line.id, "name": line.name,
                "category": line.category, "color": line.color,
            },
        })

    station_features = [
        {
            "type": "Feature",
            "geometry": {"type": "Point", "coordinates": [s.lon, s.lat]},
            "properties": {
                "id": s.id, "gid": s.gid, "name": s.name, "line_id": s.line_id,
                "line_name": net.lines[s.line_id].name,
                "color": net.lines[s.line_id].color,
            },
        }
        for s in net.stations
    ]

    return {
        "lines": {"type": "FeatureCollection", "features": line_features},
        "stations": {"type": "FeatureCollection", "features": station_features},
    }


# --- シナリオ CRUD ---

@app.get("/api/scenarios")
def list_scenarios():
    return db.list_scenarios()


@app.post("/api/scenarios", status_code=201)
def create_scenario(body: ScenarioCreate):
    return db.create_scenario(body.name, body.description,
                              [l.model_dump() for l in body.lines])


def _get_or_404(scenario_id: str) -> dict:
    sc = db.get_scenario(scenario_id)
    if sc is None:
        raise HTTPException(404, "シナリオが見つかりません")
    return sc


@app.get("/api/scenarios/{scenario_id}")
def get_scenario(scenario_id: str):
    return _get_or_404(scenario_id)


@app.put("/api/scenarios/{scenario_id}")
def update_scenario(scenario_id: str, body: ScenarioUpdate):
    _get_or_404(scenario_id)
    return db.update_scenario(
        scenario_id,
        name=body.name,
        description=body.description,
        lines=[l.model_dump() for l in body.lines] if body.lines is not None else None,
    )


@app.delete("/api/scenarios/{scenario_id}", status_code=204)
def delete_scenario(scenario_id: str):
    if not db.delete_scenario(scenario_id):
        raise HTTPException(404, "シナリオが見つかりません")


@app.post("/api/scenarios/{scenario_id}/duplicate", status_code=201)
def duplicate_scenario(scenario_id: str):
    sc = _get_or_404(scenario_id)
    return db.create_scenario(f"{sc['name']} のコピー", sc["description"], sc["lines"])


# --- 分析 ---

def _params_with_breaks(breaks_min: list[float] | None) -> Params:
    if not breaks_min:
        return Params()
    breaks = tuple(sorted(float(b) for b in breaks_min if 0 < b <= 180))
    if not breaks:
        raise HTTPException(422, "breaks_min が不正です")
    return Params(breaks_min=breaks)


def _scenario_for(scenario_id: str | None) -> dict | None:
    if not scenario_id:
        return None
    sc = _get_or_404(scenario_id)
    has_line = any(len(l.get("stations", [])) >= 2 for l in sc["lines"])
    return sc if has_line else None


@app.post("/api/analysis/isochrone")
def analysis_isochrone(body: IsochroneRequest):
    net = get_network()
    params = _params_with_breaks(body.breaks_min)
    origin = tuple(body.origin)

    before = compute_isochrone(net, get_base_graph(), origin, params)
    scenario = _scenario_for(body.scenario_id)
    after = None
    if scenario:
        after = compute_isochrone(net, get_scenario_graph(scenario), origin, params)

    summary = []
    for i, row in enumerate(before["summary"]):
        after_row = after["summary"][i] if after else None
        summary.append({
            "max_min": row["max_min"],
            "area_km2_before": row["area_km2"],
            "area_km2_after": after_row["area_km2"] if after_row else None,
            "population_before": row["population"],
            "population_after": after_row["population"] if after_row else None,
            "stations_before": row["stations"],
            "stations_after": after_row["stations"] if after_row else None,
        })

    return {
        "origin": list(origin),
        "breaks_min": list(params.breaks_min),
        "before": before["bands"],
        "after": after["bands"] if after else None,
        "summary": summary,
    }


@app.post("/api/analysis/route")
def analysis_route(body: RouteRequest):
    params = Params()
    origin, dest = tuple(body.origin), tuple(body.destination)

    before = shortest_route(get_base_graph(), origin, dest, params)
    scenario = _scenario_for(body.scenario_id)
    after = None
    if scenario:
        after = shortest_route(get_scenario_graph(scenario), origin, dest, params)

    if before is None and after is None:
        raise HTTPException(422, "経路が見つかりません(出発地・目的地が駅から遠すぎます)")
    return {"before": before, "after": after}
