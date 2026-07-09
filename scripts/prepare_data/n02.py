"""国土数値情報 鉄道データ(N02)からのネットワーク生成(Phase 2 予定・未実装)。

公式データによる高精度なネットワーク(正確な線形・最新の駅)を生成するモジュール。
nlftp.mlit.go.jp へのアクセスが必要なため、ローカル環境での実行を想定する。

実装計画:
  1. https://nlftp.mlit.go.jp/ksj/gml/data/N02/N02-<年度>/N02-<年度>_GML.zip を取得
  2. geopandas(+pyogrio)で RailroadSection / Station レイヤーを読込
  3. (事業者, 路線)ごとに区間ジオメトリから位相グラフを構築
     - 座標を丸めてノード化し、区間をエッジ(長さ付き)として登録
  4. 駅(N02 では線分)を最寄りのグラフノードにスナップ
  5. 各駅から他の駅ノードで探索を打ち切る Dijkstra を行い、
     「間に他駅を挟まない駅ペア」を隣接駅リンクとして抽出(分岐にも頑健)
  6. 駅名+近接距離で駅グループ(gid 相当)を構成し、build_network.py と
     同じスキーマの network.json を出力

必要ライブラリ: geopandas, shapely, pyogrio
"""

from __future__ import annotations


def build_from_n02(zip_path: str, area_bbox: list[float]) -> dict:
    raise NotImplementedError(
        "N02 ソースは Phase 2 で実装予定です。"
        "当面は build_network.py の japan-train-data ソースを使用してください。"
    )
