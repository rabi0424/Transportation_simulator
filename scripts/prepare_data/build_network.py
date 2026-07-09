#!/usr/bin/env python3
"""既存鉄道ネットワークデータの生成スクリプト。

公開データから正規化済みネットワーク(data/<area>/network.json)を生成する。

対応ソース:
  japan-train-data (既定)
      npm パッケージ japan-train-data (MIT License, 駅データ.jp 系。2017年頃時点)。
      路線ごとの駅順・駅座標・駅グループID(gid)を含む。node が必要。
  n02 (未実装・Phase 2)
      国土数値情報 鉄道データ N02(国土交通省)。scripts/prepare_data/n02.py 参照。

使い方:
  python3 scripts/prepare_data/build_network.py --area keihanshin
  python3 scripts/prepare_data/build_network.py --area keihanshin --cache-dir /tmp/cache

出力 network.json のスキーマ:
  meta     : source, generated_note, bbox, category_defaults, excluded_notes
  lines    : [{id, name, category, color, speed_kmh, headway_min}]
  stations : [{id, gid, name, line_id, lon, lat}]   # 路線ごとの駅ノード
  links    : [{from, to, line_id, dist_km, time_min}]  # 隣接駅間(無向)

乗換リンクは含めない(gid と座標から計算エンジンが実行時に生成する)。
"""

from __future__ import annotations

import argparse
import json
import math
import subprocess
import sys
import tarfile
import urllib.request
from pathlib import Path

NPM_TARBALL = "https://registry.npmjs.org/japan-train-data/-/japan-train-data-0.6.0.tgz"

REPO_ROOT = Path(__file__).resolve().parents[2]

AREAS = {
    # 京阪神エリア: 姫路〜大津・京都〜奈良〜和歌山市近郊まで
    "keihanshin": {"bbox": [134.4, 34.15, 136.4, 35.40]},
}

# 路線カテゴリごとの既定値(表定速度 km/h, 運行間隔 分, 代表色)
# speed_kmh は停車時間込みの「表定速度」。速達列車が主体の路線は SPEED_OVERRIDES で
# 速達列車相当の表定速度に引き上げる(利用可能な最速サービスの近似)。
CATEGORY_DEFAULTS = {
    "jr": {"speed_kmh": 42.0, "headway_min": 8.0, "color": "#1E50A2"},
    "private": {"speed_kmh": 36.0, "headway_min": 7.0, "color": "#B0752F"},
    "metro": {"speed_kmh": 30.0, "headway_min": 5.0, "color": "#CE2F68"},
    "newtransit": {"speed_kmh": 27.0, "headway_min": 7.0, "color": "#5D9E52"},
    "tram": {"speed_kmh": 13.0, "headway_min": 6.0, "color": "#7A7A3A"},
}

# 速達列車(新快速・快速急行等)主体路線の表定速度上書き(路線名の部分一致・先勝ち)
SPEED_OVERRIDES = [
    ("琵琶湖線", 70.0),
    ("JR神戸線", 70.0),
    ("近鉄京都線", 45.0),
    ("京都線", 70.0),          # JR京都線(名称が「京都線」のみのため近鉄京都線を先に判定)
    ("JR湖西線", 60.0),
    ("大阪環状線", 33.0),
    ("JR東西線", 40.0),
    ("大和路線", 50.0),
    ("阪和線", 50.0),
    ("JR宝塚線", 50.0),
    ("学研都市線", 45.0),
    ("近鉄大阪線", 50.0),
    ("近鉄奈良線", 46.0),
    ("近鉄南大阪線", 45.0),
    ("阪急京都本線", 46.0),
    ("阪急神戸本線", 42.0),
    ("阪急宝塚本線", 38.0),
    ("京阪本線", 42.0),
    ("阪神本線", 40.0),
    ("山陽電鉄本線", 42.0),
    ("南海本線", 46.0),
    ("南海高野線", 40.0),
    ("泉北高速鉄道線", 40.0),
]

# 事業者・路線の代表色(路線名の部分一致で先勝ち)
COLOR_RULES = [
    ("御堂筋線", "#E5171F"),
    ("谷町線", "#522886"),
    ("四つ橋線", "#0078BA"),
    ("大阪市営地下鉄中央線", "#019A66"),
    ("千日前線", "#E44D93"),
    ("堺筋線", "#814721"),
    ("長堀鶴見緑地線", "#A9CC51"),
    ("今里筋線", "#EE7B1A"),
    ("京都市営地下鉄烏丸線", "#00A040"),
    ("京都市営地下鉄東西線", "#D6001C"),
    ("神戸市営地下鉄", "#008542"),
    ("阪急", "#800022"),
    ("阪神", "#005BAC"),
    ("京阪", "#00A32E"),
    ("近鉄", "#D6600F"),
    ("南海", "#0C6E4F"),
    ("泉北", "#2A5CAA"),
    ("北大阪急行", "#C8161D"),
    ("大阪モノレール", "#0B74BE"),
    ("ポートライナー", "#0093D3"),
    ("六甲ライナー", "#77B22C"),
    ("山陽電鉄", "#C1272D"),
    ("能勢電鉄", "#B15EA4"),
    ("神戸電鉄", "#E60012"),
    ("神戸高速", "#555555"),
    ("阪堺", "#0A8F5B"),
]

# ネットワークから除外する路線(路線名の部分一致)
EXCLUDE_PATTERNS = ["ケーブル", "ロープウェイ", "索道", "リフト"]

# 直通運転している路線ペア(路線名、完全一致)。共有する駅グループ(gid)で
# 乗換なしの「直通リンク」(1分)を張る
THROUGH_PAIRS = [
    ("琵琶湖線", "京都線"),
    ("JR湖西線", "京都線"),
    ("京都線", "JR神戸線(大阪~神戸)"),
    ("JR神戸線(大阪~神戸)", "JR神戸線(神戸~姫路)"),
    ("JR宝塚線", "JR東西線"),
    ("JR東西線", "学研都市線"),
    ("大和路線", "大阪環状線"),
    ("阪和線(天王寺~和歌山)", "大阪環状線"),
    ("阪和線(天王寺~和歌山)", "JR関西空港線"),
    ("近鉄難波線", "近鉄奈良線"),
    ("近鉄難波線", "近鉄大阪線"),
    ("近鉄大阪線", "近鉄奈良線"),   # 快速急行の上本町~布施経由を近似
    ("近鉄京都線", "近鉄奈良線"),
    ("近鉄京都線", "近鉄橿原線"),
    ("阪神なんば線", "近鉄難波線"),
    ("阪神本線", "阪神なんば線"),
    ("京阪本線", "京阪鴨東線"),
    ("京阪本線", "京阪中之島線"),
    ("大阪市営地下鉄御堂筋線", "北大阪急行電鉄"),
    ("大阪市営地下鉄中央線", "近鉄けいはんな線"),
    ("大阪市営地下鉄堺筋線", "阪急千里線"),
    ("阪急千里線", "阪急京都本線"),
    ("南海本線", "南海空港線"),
    ("南海高野線", "泉北高速鉄道線"),
    ("神戸高速東西線", "阪急神戸本線"),
    ("神戸高速東西線", "阪神本線"),
    ("神戸高速東西線", "山陽電鉄本線"),
    ("神戸高速南北線", "有馬線"),   # 神戸電鉄有馬線
]
THROUGH_LINK_MIN = 1.0  # 直通リンクの所要時間(分)

DETOUR_FACTOR = 1.1   # 駅間直線距離 → 営業キロ近似の迂回係数

FLATTEN_JS = r"""
const d = require(process.argv[1]);
const lines = d.lines.map(l => ({
  id: l.id, name: l.name.ja,
  stations: l.stations.map(s => ({
    id: s.id, gid: s.gid, name: s.name.ja,
    lat: s.location && s.location.lat, lng: s.location && s.location.lng
  }))
}));
process.stdout.write(JSON.stringify(lines));
"""


def haversine_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    r = 6371.0
    p1, p2 = math.radians(lat1), math.radians(lat2)
    dp, dl = math.radians(lat2 - lat1), math.radians(lon2 - lon1)
    a = math.sin(dp / 2) ** 2 + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    return 2 * r * math.asin(math.sqrt(a))


def fetch_source(cache_dir: Path) -> list[dict]:
    """npm から japan-train-data を取得し、路線ごとの駅順データに平坦化する。"""
    cache_dir.mkdir(parents=True, exist_ok=True)
    flat = cache_dir / "japan-train-data-flat.json"
    if flat.exists():
        return json.loads(flat.read_text())

    tgz = cache_dir / "japan-train-data.tgz"
    if not tgz.exists():
        print(f"downloading {NPM_TARBALL} ...")
        urllib.request.urlretrieve(NPM_TARBALL, tgz)
    pkg_dir = cache_dir / "japan-train-data-pkg"
    if not (pkg_dir / "package" / "dist" / "bundle.cjs.js").exists():
        with tarfile.open(tgz) as tf:
            tf.extractall(pkg_dir, filter="data")

    bundle = pkg_dir / "package" / "dist" / "bundle.cjs.js"
    proc = subprocess.run(
        ["node", "-e", FLATTEN_JS, str(bundle)],
        capture_output=True, text=True, check=True,
    )
    flat.write_text(proc.stdout)
    return json.loads(proc.stdout)


def categorize(line_id: int, name: str) -> str:
    if "新幹線" in name:
        return "jr"
    if "地下鉄" in name or name in ("ニュートラム", "ポートライナー", "六甲ライナー"):
        return "metro" if "地下鉄" in name else "newtransit"
    if "モノレール" in name:
        return "newtransit"
    if name.startswith("阪堺") or name.startswith("京福電鉄"):
        return "tram"
    # 駅データ.jp の路線コードは JR が 1xxxx
    if line_id < 20000 or name.startswith("JR") or name in ("琵琶湖線", "大和路線", "学研都市線", "嵯峨野線", "大阪環状線", "きのくに線", "羽衣線", "万葉まほろば線", "おおさか東線"):
        return "jr"
    return "private"


def line_color(name: str, category: str) -> str:
    for pat, color in COLOR_RULES:
        if pat in name:
            return color
    return CATEGORY_DEFAULTS[category]["color"]


def line_speed(name: str, category: str) -> float:
    for pat, speed in SPEED_OVERRIDES:
        if pat in name:
            return speed
    return CATEGORY_DEFAULTS[category]["speed_kmh"]


def build(area: str, raw_lines: list[dict]) -> dict:
    bbox = AREAS[area]["bbox"]
    lon_min, lat_min, lon_max, lat_max = bbox

    def in_bbox(s: dict) -> bool:
        return (
            s.get("lng") is not None and s.get("lat") is not None
            and lon_min <= s["lng"] <= lon_max and lat_min <= s["lat"] <= lat_max
        )

    seen_line_ids: set[int] = set()
    out_lines, out_stations, out_links = [], [], []
    excluded = []

    for line in raw_lines:
        lid = line["id"]
        name = line["name"]
        if lid in seen_line_ids:
            continue
        seen_line_ids.add(lid)
        if any(p in name for p in EXCLUDE_PATTERNS):
            continue
        stations = [s for s in line["stations"]]
        inside = [s for s in stations if in_bbox(s)]
        if len(inside) < 2:
            if 2 <= len(stations) and inside:
                excluded.append(name)
            continue

        category = categorize(lid, name)
        speed = line_speed(name, category)
        out_lines.append({
            "id": str(lid),
            "name": name,
            "category": category,
            "color": line_color(name, category),
            "speed_kmh": speed,
            "headway_min": CATEGORY_DEFAULTS[category]["headway_min"],
        })

        # 駅ノード(bbox 内のみ)と、元の駅順で連続する bbox 内ペアのリンク
        for s in inside:
            out_stations.append({
                "id": f"{lid}_{s['id']}",
                "gid": s["gid"],
                "name": s["name"],
                "line_id": str(lid),
                "lon": round(s["lng"], 6),
                "lat": round(s["lat"], 6),
            })
        for a, b in zip(stations, stations[1:]):
            if not (in_bbox(a) and in_bbox(b)):
                continue
            dist = haversine_km(a["lng"], a["lat"], b["lng"], b["lat"]) * DETOUR_FACTOR
            time_min = max(1.0, dist / speed * 60.0)
            out_links.append({
                "from": f"{lid}_{a['id']}",
                "to": f"{lid}_{b['id']}",
                "line_id": str(lid),
                "dist_km": round(dist, 3),
                "time_min": round(time_min, 2),
            })

    # --- 直通運転リンク ---
    def norm(name: str) -> str:
        # 括弧・チルダ・波ダッシュ等の記号は文字コード差異が紛らわしいため除去して照合
        drop = "\u0028\u0029\uFF08\uFF09\u007E\uFF5E\u301C\u30FB\u0020\u3000"
        return "".join(c for c in name if c not in drop)

    name_to_lid = {norm(l["name"]): l["id"] for l in out_lines}
    gid_to_station: dict[tuple[str, object], str] = {}
    for s in out_stations:
        gid_to_station[(s["line_id"], s["gid"])] = s["id"]
    gids_by_line: dict[str, set] = {}
    for s in out_stations:
        gids_by_line.setdefault(s["line_id"], set()).add(s["gid"])

    through_count = 0
    unmatched_pairs = []
    for name_a, name_b in THROUGH_PAIRS:
        la, lb = name_to_lid.get(norm(name_a)), name_to_lid.get(norm(name_b))
        if la is None or lb is None:
            unmatched_pairs.append(f"{name_a}×{name_b}")
            continue
        shared = gids_by_line.get(la, set()) & gids_by_line.get(lb, set())
        for gid in shared:
            out_links.append({
                "from": gid_to_station[(la, gid)],
                "to": gid_to_station[(lb, gid)],
                "line_id": la,
                "dist_km": 0.0,
                "time_min": THROUGH_LINK_MIN,
                "through": True,
            })
            through_count += 1
        if not shared:
            unmatched_pairs.append(f"{name_a}×{name_b} (共有駅なし)")
    if unmatched_pairs:
        print("[warn] 直通ペア未解決:", "; ".join(unmatched_pairs))
    print(f"直通リンク: {through_count} 本")

    return {
        "meta": {
            "area": area,
            "source": "japan-train-data 0.6.0 (npm, MIT License; 駅データ.jp 系データ・2017年頃時点)",
            "generated_note": (
                "駅間所要時間は 直線距離×迂回係数1.2÷表定速度 の概算(速度は停車込みの表定速度)。"
                "新幹線・神戸市営地下鉄海岸線など一部路線はソースデータに含まれない。"
            ),
            "bbox": bbox,
            "category_defaults": CATEGORY_DEFAULTS,
            "detour_factor": DETOUR_FACTOR,
            "clipped_lines": excluded,
        },
        "lines": out_lines,
        "stations": out_stations,
        "links": out_links,
    }


def main() -> None:
    ap = argparse.ArgumentParser(description=__doc__)
    ap.add_argument("--area", default="keihanshin", choices=sorted(AREAS))
    ap.add_argument("--source", default="japan-train-data", choices=["japan-train-data", "n02"])
    ap.add_argument("--cache-dir", type=Path, default=REPO_ROOT / ".cache" / "prepare_data")
    ap.add_argument("--out", type=Path, default=None,
                    help="出力パス(既定: data/<area>/network.json)")
    args = ap.parse_args()

    if args.source == "n02":
        sys.exit("N02 ソースは未実装です(Phase 2 予定)。scripts/prepare_data/n02.py を参照してください。")

    raw = fetch_source(args.cache_dir)
    net = build(args.area, raw)

    out = args.out or REPO_ROOT / "data" / args.area / "network.json"
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(json.dumps(net, ensure_ascii=False, separators=(",", ":")), encoding="utf-8")
    print(f"wrote {out}")
    print(f"  lines={len(net['lines'])} stations={len(net['stations'])} links={len(net['links'])}")


if __name__ == "__main__":
    main()
