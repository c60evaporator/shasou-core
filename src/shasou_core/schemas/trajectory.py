"""trajectory 成果物のスキーマ。

自己位置推定バックエンド (PPK+INS / LIO / NDT / CARLA-GT) は、共通形式の
trajectory 成果物を出力する。nuScenes 変換器はこれを消費して ego_pose を作る。

設計 (選択肢 B: 1 ドライブ 1 対多 backend)
------------------------------------------
1 つの drive から複数 backend の軌跡が併存できる。各成果物は自身の backend を
メタデータに刻む (来歴)。manifest.ego_pose_backend は「推奨手法」であって、
実際に生成された軌跡の backend と一致する必要はない。

座標系
------
軌跡は location ごとに固定した local ENU 原点 (datum) を持つ右手系で、これを
nuScenes の global frame として扱う。datum の測地座標をメタデータに記録し、
studio の PostGIS (SRID 4326) への変換はこの原点情報から一意に決まる。

成果物の物理形式
----------------
- メタデータ: TrajectoryMetadata (JSON/YAML)
- 軌跡本体:   Parquet (列は TRAJECTORY_COLUMNS)。1 行 = 1 TrajectoryPoint。
              io.trajectory_io がメタデータと本体をまとめて読み書きする。
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field, model_validator

from ..version import SCHEMA_VERSION
from .common import (
    EgoPoseBackend,
    FrozenModel,
    Pose,
    ShasouModel,
    TimestampNs,
)


class PoseQuality(str, Enum):
    """各軌跡点の品質区分。backend 横断で正規化した値。

    変換パイプラインが「品質が低い区間を scene 化しない / 警告フラグを付ける」
    ゲートに使う。backend 固有の生スコア (RTK fix 状態や NDT スコア) は
    raw_quality に数値で残す。
    """

    HIGH = "high"        # RTK fix / 良好なマッチング
    MEDIUM = "medium"    # RTK float / 中程度
    LOW = "low"          # 単独測位相当 / マッチング不良
    INVALID = "invalid"  # 使用不可 (欠測・発散)


class Datum(FrozenModel):
    """local ENU 原点の測地座標。軌跡座標系の基準。

    location 単位で固定し、同一 location の複数 drive が同じ座標系に乗るように
    する。studio の SRID 4326 変換はこの原点から決まる。
    """

    latitude: float = Field(ge=-90.0, le=90.0)
    longitude: float = Field(ge=-180.0, le=180.0)
    altitude: float = Field(description="楕円体高またはジオイド高 (メートル)")
    geoid_reference: str = Field(
        default="WGS84",
        description="測地系。CARLA では OpenDRIVE geoReference 由来",
    )


class TrajectoryPoint(FrozenModel):
    """軌跡上の 1 点。datum 基準の local ENU (右手系) における pose。

    Parquet 本体の 1 行に対応する。列名は TRAJECTORY_COLUMNS を参照。
    """

    timestamp: TimestampNs
    pose: Pose
    quality: PoseQuality
    raw_quality: float | None = Field(
        default=None,
        description="backend 固有の生スコア (RTK 状態コード, NDT スコア等)",
    )


class TrajectoryMetadata(ShasouModel):
    """1 つの軌跡成果物のメタデータ。"""

    drive_id: str
    backend: EgoPoseBackend = Field(
        description="この成果物を実際に生成した手法 (来歴)。manifest の推奨手法とは"
        "独立で、1 drive に複数 backend の成果物が併存しうる",
    )
    backend_version: str = Field(
        description="生成器のバージョン。同一 backend でも改良で作り直せる",
    )
    schema_version: str = SCHEMA_VERSION
    datum: Datum
    frame_id: str = Field(
        default="map",
        description="軌跡の座標フレーム。datum を原点とする local ENU",
    )
    point_count: int = Field(ge=0)
    start_timestamp: TimestampNs
    end_timestamp: TimestampNs

    @model_validator(mode="after")
    def _check_time_order(self) -> "TrajectoryMetadata":
        if self.end_timestamp < self.start_timestamp:
            raise ValueError("end_timestamp < start_timestamp")
        return self

    def artifact_key(self) -> str:
        """成果物を一意に識別するキー (ファイル名等に使う)。

        drive + backend + version で「どの軌跡版か」を表す。同一 drive の
        複数 backend 成果物が衝突しない。
        """
        return f"{self.drive_id}__{self.backend.value}__{self.backend_version}"


# --------------------------------------------------------------------------
# Parquet 本体の列仕様
# --------------------------------------------------------------------------
# io.trajectory_io がこの仕様で TrajectoryPoint 列を読み書きする。
# quaternion は ROS 順 (x, y, z, w)。時刻は ns 整数。
TRAJECTORY_COLUMNS: tuple[str, ...] = (
    "timestamp",   # int64 (ns)
    "x", "y", "z",         # float64, datum 基準 local ENU
    "qx", "qy", "qz", "qw",  # float64, ROS 順
    "quality",     # string (PoseQuality の値)
    "raw_quality",  # float64 nullable
)
