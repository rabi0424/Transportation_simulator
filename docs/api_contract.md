# API 契約(Phase 1)

バックエンド: FastAPI(ポート 8000)。フロントエンドは Vite dev proxy で `/api` → `http://localhost:8000` に転送する。
エラーは FastAPI 標準の `{"detail": "..."}`。座標は常に `[lon, lat]`(GeoJSON 準拠)。

## GET /api/config

```json
{
  "area": "keihanshin",
  "map_center": [135.5, 34.70],
  "map_zoom": 10,
  "bbox": [134.4, 34.15, 136.4, 35.40],
  "breaks_min_default": [15, 30, 45, 60],
  "population_available": false
}
```

## GET /api/network/geojson

既存ネットワーク。

```json
{
  "lines": { "type": "FeatureCollection", "features": [
    { "type": "Feature",
      "geometry": { "type": "MultiLineString", "coordinates": [...] },
      "properties": { "id": "11623", "name": "大阪環状線", "category": "jr", "color": "#1E50A2" } }
  ]},
  "stations": { "type": "FeatureCollection", "features": [
    { "type": "Feature",
      "geometry": { "type": "Point", "coordinates": [135.5, 34.7] },
      "properties": { "id": "11623_1162301", "gid": 1162301, "name": "大阪",
                       "line_id": "11623", "line_name": "大阪環状線", "color": "#1E50A2" } }
  ]}
}
```

category は `jr | private | metro | newtransit | tram`。

## シナリオ CRUD

シナリオオブジェクト(完全形):

```json
{
  "id": "c9b1...",
  "name": "なにわ筋線案A",
  "description": "",
  "lines": [
    { "name": "新線1", "color": "#FF3B30", "speed_kmh": 35.0, "headway_min": 6.0,
      "stations": [
        { "name": "新大阪", "lon": 135.5, "lat": 34.73, "snap_station_id": "11602_..." },
        { "name": "中之島新駅", "lon": 135.49, "lat": 34.69, "snap_station_id": null }
      ] }
  ],
  "created_at": "2026-07-09T00:00:00+00:00",
  "updated_at": "2026-07-09T00:00:00+00:00"
}
```

- `snap_station_id`: 既存駅にスナップして置いた駅はその駅IDを持つ(乗換接続の確実化)。自由配置は null。
- `GET  /api/scenarios` → `[{ "id", "name", "description", "line_count", "updated_at" }]`
- `POST /api/scenarios` body `{name, description?, lines?}` → 201, 完全形
- `GET  /api/scenarios/{id}` → 完全形
- `PUT  /api/scenarios/{id}` body `{name?, description?, lines?}` → 完全形
- `DELETE /api/scenarios/{id}` → 204
- `POST /api/scenarios/{id}/duplicate` → 201, 完全形(名前に「のコピー」付与)

## POST /api/analysis/isochrone

```json
{ "origin": [135.50, 34.70], "scenario_id": "c9b1...", "breaks_min": [15, 30, 45, 60] }
```

`scenario_id` が null/省略なら整備前のみ計算する。応答:

```json
{
  "origin": [135.50, 34.70],
  "breaks_min": [15, 30, 45, 60],
  "before": { "type": "FeatureCollection", "features": [
     { "type": "Feature", "geometry": { "type": "MultiPolygon", "coordinates": [...] },
       "properties": { "min_min": 0, "max_min": 15 } }
  ]},
  "after": null,
  "summary": [
    { "max_min": 15, "area_km2_before": 12.3, "area_km2_after": null,
      "population_before": null, "population_after": null,
      "stations_before": 10, "stations_after": null }
  ]
}
```

- バンドは**非重複リング**(`min_min`〜`max_min` の帯)。`summary` は**累積値**(`max_min` 以内)。
- `population_*` は人口メッシュデータ未整備の場合 null。
- `after` はシナリオ指定時のみ FeatureCollection。

## POST /api/analysis/route

```json
{ "origin": [135.50, 34.70], "destination": [135.76, 35.0], "scenario_id": "c9b1..." }
```

応答:

```json
{
  "before": {
    "total_min": 42.5,
    "legs": [
      { "type": "walk", "line_name": null, "line_color": null,
        "from_name": "出発地", "to_name": "大阪", "minutes": 8.0,
        "coords": [[135.5,34.7],[135.498,34.702]] },
      { "type": "ride", "line_name": "京都線", "line_color": "#1E50A2",
        "from_name": "大阪", "to_name": "京都", "minutes": 28.0,
        "coords": [[...],[...]] },
      { "type": "transfer", "line_name": "烏丸線", "line_color": "#00A040",
        "from_name": "京都", "to_name": "京都", "minutes": 5.0, "coords": [[...],[...]] }
    ]
  },
  "after": null
}
```

- `type`: `walk`(出発・到着の徒歩)/ `ride`(乗車。途中駅はまとめて1レグ、coords は経由駅列)/ `transfer`(乗換徒歩+待ち)。
- `after` はシナリオ指定時のみ。`scenario_id` 省略時は null。
- 到達不能の場合は該当側を `null` とし、両方不能なら 422。
