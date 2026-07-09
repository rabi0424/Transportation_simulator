"""API リクエスト/レスポンスの Pydantic モデル。"""

from __future__ import annotations

from pydantic import BaseModel, Field


class NewStationIn(BaseModel):
    name: str = ""
    lon: float
    lat: float
    snap_station_id: str | None = None


class NewLineIn(BaseModel):
    name: str = "新線"
    color: str = "#FF3B30"
    speed_kmh: float = Field(default=35.0, gt=0, le=300)
    headway_min: float = Field(default=6.0, gt=0, le=120)
    stations: list[NewStationIn] = []


class ScenarioCreate(BaseModel):
    name: str
    description: str = ""
    lines: list[NewLineIn] = []


class ScenarioUpdate(BaseModel):
    name: str | None = None
    description: str | None = None
    lines: list[NewLineIn] | None = None


class IsochroneRequest(BaseModel):
    origin: tuple[float, float]
    scenario_id: str | None = None
    breaks_min: list[float] | None = None


class RouteRequest(BaseModel):
    origin: tuple[float, float]
    destination: tuple[float, float]
    scenario_id: str | None = None
