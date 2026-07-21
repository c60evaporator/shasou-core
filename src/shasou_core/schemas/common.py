"""全スキーマが共有する基本型。

- Token:          nuScenes 互換の 32 文字小文字 hex。uuid4 (新規採番) または
                  uuid5 (決定的導出) の .hex 表現。
- TimestampNs:    エポックからのナノ秒整数 (constants.py の単位規約を参照)。
- QuaternionXYZW: ROS 順 (x, y, z, w)。nuScenes の (w, x, y, z) への並び替えは
                  エクスポータの責務。
"""

from __future__ import annotations

import math
import uuid
from enum import Enum
from typing import Annotated

from pydantic import BaseModel, ConfigDict, Field, StringConstraints, model_validator

from ..constants import NS_PER_SEC, NS_PER_US

# --------------------------------------------------------------------------
# 基底モデル
# --------------------------------------------------------------------------


class ShasouModel(BaseModel):
    """全スキーマの基底。未知フィールドを拒否して契約違反を早期検出する。"""

    model_config = ConfigDict(extra="forbid")


class FrozenModel(ShasouModel):
    """不変な値型 (Vector3 等) の基底。"""

    model_config = ConfigDict(extra="forbid", frozen=True)


# --------------------------------------------------------------------------
# Token
# --------------------------------------------------------------------------

TOKEN_PATTERN = r"^[0-9a-f]{32}$"
Token = Annotated[str, StringConstraints(pattern=TOKEN_PATTERN)]

# shasou 固有の uuid5 名前空間。決定的導出トークンの再現性を保証する。
SHASOU_UUID_NAMESPACE = uuid.uuid5(uuid.NAMESPACE_DNS, "shasou")


def new_token() -> str:
    """新規トークンを採番する (uuid4)。"""
    return uuid.uuid4().hex


def derived_token(*parts: str) -> str:
    """決定的にトークンを導出する (uuid5)。

    例: エクスポート時の instance token = derived_token(track_token, scene_token)、
    ego_pose token = derived_token(sample_data_token, "ego_pose")。
    同じ入力からは常に同じトークンが得られ、再エクスポートが安定する。
    """
    if not parts:
        raise ValueError("derived_token requires at least one part")
    return uuid.uuid5(SHASOU_UUID_NAMESPACE, "/".join(parts)).hex


# --------------------------------------------------------------------------
# 時刻
# --------------------------------------------------------------------------

TimestampNs = Annotated[int, Field(ge=0, description="エポックからのナノ秒整数")]


def seconds_to_ns(seconds: float) -> int:
    """秒 (float) をナノ秒整数へ変換する。

    CARLA の timestamp.elapsed_seconds 等、float 秒からの変換はすべて
    この関数を経由すること (ミリ秒を nanosec に入れる類の事故を防ぐ)。
    """
    return round(seconds * NS_PER_SEC)


def ns_to_seconds(ns: int) -> float:
    return ns / NS_PER_SEC


def ns_to_us(ns: int) -> int:
    """ナノ秒をマイクロ秒へ切り捨て変換する (nuScenes エクスポート用)。"""
    return ns // NS_PER_US


# --------------------------------------------------------------------------
# 列挙型
# --------------------------------------------------------------------------


class Modality(str, Enum):
    CAMERA = "camera"
    LIDAR = "lidar"
    RADAR = "radar"
    GNSS = "gnss"
    IMU = "imu"
    VEHICLE = "vehicle"  # 車両状態 (drive_state / pedals 等)


class DataSource(str, Enum):
    """ドライブの出自。トピックセットの差分 (topics.py) と対応する。"""

    CARLA = "carla"
    REAL = "real"


class EgoPoseBackend(str, Enum):
    """自己位置推定バックエンド。共有語彙 (選択肢 B)。

    2 箇所で使われるが意味づけが異なる:
    - manifest.ego_pose_backend: このドライブの *推奨/既定* 手法 (弱い宣言)。
      後から他手法で軌跡を作っても矛盾しない。
    - TrajectoryMetadata.backend: この軌跡成果物を *実際に作った* 手法 (来歴)。
    1 ドライブから複数 backend の軌跡が併存できる (1 対多)。値集合は共有し、
    1 対 1 制約は課さない。
    """

    PPK_INS = "ppk-ins"          # A: PPK + INS (生観測 + 電子基準点)
    LIO_GRAPH = "lio-graph"      # B: LIO + ポーズグラフ最適化
    NDT_MAP = "ndt-map"          # C: 事前点群地図 + NDT マッチング
    CARLA_GT = "carla-gt"        # CARLA 特権情報 (真値)


# --------------------------------------------------------------------------
# 幾何値型
# --------------------------------------------------------------------------


class Vector3(FrozenModel):
    x: float
    y: float
    z: float


class QuaternionXYZW(FrozenModel):
    """単位クォータニオン。ROS 順 (x, y, z, w) で格納する。

    許容誤差 1e-3 以内で正規化されていることを検証する。
    nuScenes の (w, x, y, z) への並び替えはエクスポータの責務。
    """

    x: float
    y: float
    z: float
    w: float

    @model_validator(mode="after")
    def _check_normalized(self) -> "QuaternionXYZW":
        norm = math.sqrt(self.x**2 + self.y**2 + self.z**2 + self.w**2)
        if abs(norm - 1.0) > 1e-3:
            raise ValueError(f"quaternion is not normalized (norm={norm:.6f})")
        return self

    def normalized(self) -> "QuaternionXYZW":
        """厳密に正規化したコピーを返す (格納前の丸め誤差の掃除用)。"""
        norm = math.sqrt(self.x**2 + self.y**2 + self.z**2 + self.w**2)
        return QuaternionXYZW(
            x=self.x / norm, y=self.y / norm, z=self.z / norm, w=self.w / norm
        )

    @classmethod
    def identity(cls) -> "QuaternionXYZW":
        return cls(x=0.0, y=0.0, z=0.0, w=1.0)


class Pose(FrozenModel):
    """位置と姿勢の組。frame は文脈 (スキーマ側) が規定する。"""

    translation: Vector3
    rotation: QuaternionXYZW
