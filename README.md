# Transportation Simulator(新設路線シミュレーター)

既存の公共交通ネットワークに新設路線計画を入力し、利用者数の予測や所要時間の
短縮効果を計算・可視化するツール(日本国内対象)。

現在 **Phase 1** 実装済み: 京阪神エリアの鉄道ネットワークを対象に、
地図上での新設路線入力、**等時圏(到達圏)の整備前後比較**、**2地点間の
経路・所要時間の整備前後比較** ができる。需要予測(利用者数)は Phase 2 で実装予定。
設計書は [docs/DESIGN.md](docs/DESIGN.md) を参照。

## 起動方法

### バックエンド(FastAPI, ポート 8000)

```bash
cd backend
pip install -r requirements.txt
uvicorn app.main:app --reload --port 8000
```

### フロントエンド(Vite + React, ポート 5173)

```bash
cd frontend
npm install
npm run dev
# http://localhost:5173 を開く(API は /api → localhost:8000 にプロキシ)
```

### テスト

```bash
cd backend && python3 -m pytest        # 計算エンジン+API の15テスト
cd frontend && npm run build           # 型チェック+ビルド
```

## 使い方

1. **路線編集** タブでシナリオを作成し、「+ 路線を追加」→ 地図クリックで駅を配置
   (既存駅の 300m 以内はスナップされ乗換駅になる)。表定速度・運行間隔・色も設定可能
2. **等時圏** タブで出発地をクリック → シナリオを選び「計算」→
   15/30/45/60 分圏の整備前後と、面積・到達駅数(人口データがあれば人口)の差分を表示
3. **経路** タブで出発地・目的地をクリック → 整備前後の経路・所要時間・短縮効果を表示

## データについて

- 既存ネットワーク: `data/keihanshin/network.json`(コミット済み)。
  生成方法・データ出典・既知の制限は [scripts/prepare_data/README.md](scripts/prepare_data/README.md) を参照
- 所要時間は表定速度ベースの概算(速達列車の停車駅は未考慮、直通運転は主要系統のみ近似)。
  **概略検討(スケッチプランニング)用**であり、正式な需要予測・B/C 算定を代替するものではない
- 500m メッシュ人口(`population_mesh.csv`)を置くと等時圏サマリーに圏内人口が出る(任意)

## 構成

```
backend/
  app/         FastAPI(ネットワーク配信・シナリオ CRUD・分析 API)
  simulator/   計算エンジン(グラフ構築・Dijkstra・等時圏。API から独立)
  tests/
frontend/      React + TypeScript + MapLibre GL JS(地理院タイル)
scripts/prepare_data/   ネットワークデータ生成
data/keihanshin/        前処理済みネットワークデータ
docs/          設計書・API 契約
```

## 技術スタック

- フロントエンド: React + TypeScript + MapLibre GL JS
- バックエンド: Python + FastAPI + shapely(等時圏ポリゴン)
- データ: japan-train-data(駅データ.jp 系, MIT)。Phase 2 で国土数値情報 N02 対応予定
