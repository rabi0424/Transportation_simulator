"""ネットワークデータ(network.json)と人口メッシュの読込。"""

from __future__ import annotations

import csv
import json
from dataclasses import dataclass, field
from pathlib import Path

from .geo import cell_from_meshcode


@dataclass
class LineInfo:
    id: str
    name: str
    category: str
    color: str
    speed_kmh: float
    headway_min: float


@dataclass
class StationRec:
    id: str
    gid: int | str | None
    name: str
    line_id: str
    lon: float
    lat: float


@dataclass
class LinkRec:
    from_id: str
    to_id: str
    line_id: str
    dist_km: float
    time_min: float


@dataclass
class Network:
    meta: dict
    lines: dict[str, LineInfo]
    stations: list[StationRec]
    links: list[LinkRec]
    population: dict[tuple[int, int], float] = field(default_factory=dict)

    @property
    def bbox(self) -> list[float]:
        return self.meta.get("bbox", [134.4, 34.15, 136.4, 35.40])


def load_network(path: str | Path) -> Network:
    data = json.loads(Path(path).read_text(encoding="utf-8"))
    lines = {
        l["id"]: LineInfo(
            id=l["id"], name=l["name"], category=l["category"], color=l["color"],
            speed_kmh=float(l["speed_kmh"]), headway_min=float(l["headway_min"]),
        )
        for l in data["lines"]
    }
    stations = [
        StationRec(
            id=s["id"], gid=s.get("gid"), name=s["name"],
            line_id=s["line_id"], lon=float(s["lon"]), lat=float(s["lat"]),
        )
        for s in data["stations"]
    ]
    links = [
        LinkRec(
            from_id=k["from"], to_id=k["to"], line_id=k["line_id"],
            dist_km=float(k["dist_km"]), time_min=float(k["time_min"]),
        )
        for k in data["links"]
    ]
    net = Network(meta=data.get("meta", {}), lines=lines, stations=stations, links=links)

    pop_path = Path(path).parent / "population_mesh.csv"
    if pop_path.exists():
        net.population = load_population(pop_path)
    return net


def load_population(path: str | Path) -> dict[tuple[int, int], float]:
    """population_mesh.csv (列: mesh_code, population) を読み込む。

    mesh_code は 9 桁の 500m メッシュコード。scripts/prepare_data/README.md 参照。
    """
    pop: dict[tuple[int, int], float] = {}
    with open(path, newline="", encoding="utf-8") as f:
        for row in csv.DictReader(f):
            try:
                cell = cell_from_meshcode(row["mesh_code"])
                pop[cell] = pop.get(cell, 0.0) + float(row["population"])
            except (KeyError, ValueError):
                continue
    return pop
