"""ネットワークデータとベースグラフの読込・キャッシュ。"""

from __future__ import annotations

import os
from functools import lru_cache
from pathlib import Path

from simulator import Network, Params, TransitGraph, build_graph, load_network

REPO_ROOT = Path(__file__).resolve().parents[2]
DEFAULT_NETWORK = REPO_ROOT / "data" / "keihanshin" / "network.json"


def network_path() -> Path:
    return Path(os.environ.get("TRANSIM_NETWORK", DEFAULT_NETWORK))


@lru_cache(maxsize=1)
def get_network() -> Network:
    return load_network(network_path())


@lru_cache(maxsize=1)
def get_base_graph() -> TransitGraph:
    return build_graph(get_network(), params=Params())


def get_scenario_graph(scenario: dict) -> TransitGraph:
    """シナリオ適用グラフ。構築は ~50ms 程度なのでリクエスト毎に生成する。"""
    return build_graph(get_network(), scenario, params=Params())
