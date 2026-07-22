"""platform 定義スキーマ。

platform は「同一のセンサ構成 (sensor_rig) と車種 (vehicle_type) で収録された
ドライブ群」をグルーピングする単位。studio が編集元 (source of truth) で、
recorder は同期して使う。同一 platform に複数の車両個体 (Vehicle) が属しうる
(フリート運用)。学習データセットの構成 (複数 platform を混ぜて学習に使うか) は
studio の責務であり core は関与しない。

calibration.py との責務分担: ChannelSpec は *構成上の宣言* (設計値・公称値。
期待する内部パラメータモデルの型参照や設計搭載位置) を持ち、実測の歪み係数・
実測搭載位置はキャリブレーション 1 回ごとの calibration.py 側が持つ。
宣言と実測の整合照合は validation.py の責務。

車両個体の物理パラメータ・CAN 仕様は vehicle.py (VehicleType / Vehicle) の責務。
platform は車種を vehicle_type (VehicleType への参照 ID) で指すだけ。
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from pydantic import Field, field_validator, model_validator

from ..constants import channel_modality, is_valid_channel_name
from .common import Modality, Pose, ShasouModel


class CameraIntrinsicsModel(str, Enum):
    """カメラ内部パラメータの型参照 (構成上の宣言)。

    実測係数は calibration.py (CameraIntrinsics) が持つ。ここでは
    「このカメラのキャリブがどのモデルで表現されるべきか」だけを宣言する。
    """

    PINHOLE_PLUMB_BOB = "pinhole_plumb_bob"  # OpenCV plumb_bob (k1,k2,p1,p2,k3)
    FISHEYE_EQUIDISTANT = "fisheye_equidistant"  # OpenCV fisheye (k1..k4)


# --------------------------------------------------------------------------
# センサ構成
# --------------------------------------------------------------------------


class CameraConfig(ShasouModel):
    """カメラの構成情報 (modality=camera のチャネルのみ)。すべて公称値。"""

    width_px: Optional[int] = Field(default=None, ge=1, description="画像幅 [px]")
    height_px: Optional[int] = Field(default=None, ge=1, description="画像高さ [px]")
    horizontal_fov_rad: Optional[float] = Field(
        default=None, gt=0, le=math.tau,
        description="水平画角 [rad] (公称値)",
    )
    intrinsics_model: Optional[CameraIntrinsicsModel] = Field(
        default=None,
        description="期待する内部パラメータモデル (実測係数は calibration 側)",
    )

    @model_validator(mode="after")
    def _resolution_pair(self) -> "CameraConfig":
        if (self.width_px is None) != (self.height_px is None):
            raise ValueError("解像度は width_px / height_px を両方指定すること")
        return self


class ChannelSpec(ShasouModel):
    """platform の sensor_rig を構成する 1 チャネルの定義。"""

    channel: str = Field(description="正規チャネル名 (CAM_FRONT 等)")
    modality: Modality
    nominal_mount: Optional[Pose] = Field(
        default=None,
        description="base_link 基準の設計搭載位置 (公称値)。カメラは光学フレーム。"
        "実測搭載位置は calibration 側",
    )
    camera: Optional[CameraConfig] = Field(
        default=None,
        description="カメラ構成情報。modality=camera のときのみ指定可",
    )

    @field_validator("channel")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not is_valid_channel_name(v):
            raise ValueError(f"チャネル名が命名規約違反: {v!r}")
        return v

    @model_validator(mode="after")
    def _camera_config_only_for_camera(self) -> "ChannelSpec":
        if self.camera is not None and self.modality != Modality.CAMERA:
            raise ValueError(
                f"{self.channel}: camera 構成は modality=camera のチャネルのみ "
                f"(宣言: {self.modality.value})"
            )
        return self


class Platform(ShasouModel):
    """platform 定義。sensor_rig (チャネル集合) + vehicle_type。

    同一 platform に複数の車両個体 (Vehicle) が属しうる。車種の物理パラメータ
    と CAN 仕様は vehicle.py の VehicleType / Vehicle が持ち、platform は
    vehicle_type で車種を参照するだけ。
    """

    platform_id: str = Field(description="platform ID (フォルダ名と一致)")
    vehicle_type: str = Field(
        description="VehicleType への参照 ID (vehicle.py の VehicleType.vehicle_type_id)",
    )
    sensor_rig: list[ChannelSpec] = Field(
        description="この platform のセンサ構成。実チャネル集合の正",
    )

    def channel_names(self) -> set[str]:
        return {c.channel for c in self.sensor_rig}

    def channels_by_modality(self, modality: Modality) -> list[str]:
        return [c.channel for c in self.sensor_rig if c.modality == modality]

    @field_validator("sensor_rig")
    @classmethod
    def _modality_matches_name(cls, v: list[ChannelSpec]) -> list[ChannelSpec]:
        # 宣言された modality がチャネル名のプレフィックスと矛盾しないこと
        for spec in v:
            inferred = channel_modality(spec.channel)
            if inferred is not None and inferred != spec.modality.value:
                raise ValueError(
                    f"{spec.channel}: 名前が示す modality ({inferred}) と "
                    f"宣言 ({spec.modality.value}) が不一致"
                )
        return v
