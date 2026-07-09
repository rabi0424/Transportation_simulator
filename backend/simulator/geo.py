"""地理計算ユーティリティ(500m メッシュ、距離)。

メッシュは JIS 標準地域メッシュの 4次(500m)メッシュに整合する内部グリッド
(i, j) を用いる: i = floor(lat * 240), j = floor(lon * 160)。
"""

from __future__ import annotations

import math

EARTH_KM_PER_DEG_LAT = 111.32
LAT_UNIT = 1.0 / 240.0  # 500m メッシュの緯度幅 (15秒)
LON_UNIT = 1.0 / 160.0  # 500m メッシュの経度幅 (22.5秒)


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def approx_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """短距離向けの正距円筒近似(等時圏のセル計算用・高速)。"""
    ky = EARTH_KM_PER_DEG_LAT
    kx = ky * math.cos(math.radians((lat1 + lat2) / 2))
    return math.hypot((lon1 - lon2) * kx, (lat1 - lat2) * ky)


def cell_of(lon: float, lat: float) -> tuple[int, int]:
    return (math.floor(lat * 240.0), math.floor(lon * 160.0))


def cell_bounds(i: int, j: int) -> tuple[float, float, float, float]:
    """(lon_min, lat_min, lon_max, lat_max)"""
    return (j * LON_UNIT, i * LAT_UNIT, (j + 1) * LON_UNIT, (i + 1) * LAT_UNIT)


def cell_center(i: int, j: int) -> tuple[float, float]:
    return ((j + 0.5) * LON_UNIT, (i + 0.5) * LAT_UNIT)


def cell_area_km2(i: int, j: int) -> float:
    lat = (i + 0.5) * LAT_UNIT
    h = EARTH_KM_PER_DEG_LAT * LAT_UNIT
    w = EARTH_KM_PER_DEG_LAT * math.cos(math.radians(lat)) * LON_UNIT
    return h * w


def meshcode_500m(lat: float, lon: float) -> str:
    """緯度経度から 9桁の 500m(4次)メッシュコードを返す。"""
    p = int(lat * 1.5)                       # 1次メッシュ 緯度
    u = int(lon) - 100                       # 1次メッシュ 経度
    lat_r = lat * 1.5 - p
    lon_r = lon - int(lon)
    q = int(lat_r * 8)                       # 2次 (0-7)
    v = int(lon_r * 8)
    lat_r = lat_r * 8 - q
    lon_r = lon_r * 8 - v
    r = int(lat_r * 10)                      # 3次 (0-9)
    w = int(lon_r * 10)
    lat_r = lat_r * 10 - r
    lon_r = lon_r * 10 - w
    s = 1 + (1 if lon_r >= 0.5 else 0) + 2 * (1 if lat_r >= 0.5 else 0)
    return f"{p:02d}{u:02d}{q}{v}{r}{w}{s}"


def cell_from_meshcode(code: str) -> tuple[int, int]:
    """500m メッシュコード → 内部グリッド (i, j)。"""
    code = code.strip()
    if len(code) != 9:
        raise ValueError(f"500m メッシュコードは 9 桁: {code!r}")
    p, u = int(code[0:2]), int(code[2:4])
    q, v, r, w, s = (int(c) for c in code[4:9])
    slat, slon = (s - 1) // 2, (s - 1) % 2
    lat0 = p * (2.0 / 3.0) + q * (1.0 / 12.0) + r * (1.0 / 120.0) + slat * LAT_UNIT
    lon0 = (100 + u) + v * (1.0 / 8.0) + w * (1.0 / 80.0) + slon * LON_UNIT
    return (round(lat0 * 240.0), round(lon0 * 160.0))
