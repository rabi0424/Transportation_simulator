"""計算パラメータ。すべて分・メートル単位の既定値を持ち、API から上書き可能。"""

from __future__ import annotations

from dataclasses import dataclass, field


@dataclass(frozen=True)
class Params:
    walk_speed_m_min: float = 80.0        # 徒歩速度 (m/分)
    transfer_penalty_min: float = 3.0     # 乗換抵抗(待ち以外の心理的・移動ロス)
    same_gid_walk_min: float = 2.0        # 同一駅(駅グループ)内の乗換歩行時間
    transfer_radius_m: float = 400.0      # 異駅間の乗換徒歩を張る最大距離
    new_station_transfer_radius_m: float = 500.0  # 新駅と既存駅の接続半径
    access_radius_m: float = 1500.0       # 出発地・目的地から駅までの徒歩上限距離
    egress_walk_cap_min: float = 15.0     # 等時圏で駅から歩ける上限時間(分)
    direct_walk_detour: float = 1.3       # 徒歩直行の迂回係数
    breaks_min: tuple[float, ...] = field(default=(15.0, 30.0, 45.0, 60.0))
