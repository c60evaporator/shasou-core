"""platform 定義スキーマ。

platform は「学習データとして一体利用できる」単位で、センサ構成 (sensor_rig)
と車種 (vehicle_type) が一致するデータをグルーピングする。studio が編集元
(source of truth) で、recorder は同期して使う。

calibration.py との責務分担: ChannelSpec は *構成上の宣言* (設計値・公称値。
期待する内部パラメータモデルの型参照や設計搭載位置) を持ち、実測の歪み係数・
実測搭載位置はキャリブレーション 1 回ごとの calibration.py 側が持つ。
宣言と実測の整合照合は validation.py の責務。
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from pydantic import Field, field_validator, model_validator

from ..constants import channel_modality, is_valid_channel_name
from .common import Modality, Pose, ShasouModel, Vector3

# --------------------------------------------------------------------------
# 車両固有パラメータの語彙
# --------------------------------------------------------------------------


class SpeedSignRule(str, Enum):
    """ソース (CAN / CARLA) の速度値の符号規則。

    shasou の契約は「m/s・後退で負」(constants.py)。ソースがこの契約と
    異なる場合にアダプタがどう変換すべきかを宣言する。
    """

    SIGNED = "signed"  # ソース速度が符号付き (後退で負)。そのまま使える
    ABS_WITH_REVERSE_FLAG = "abs_with_reverse_flag"  # 速度は常に非負。reverse フラグで符号を付与


class BrakeNormalization(str, Enum):
    """pedals トピックの brake=1.0 が何を意味するか。"""

    STROKE = "stroke"  # 最大ペダルストロークを 1.0 とする
    PRESSURE = "pressure"  # 最大ブレーキ液圧を 1.0 とする
    SWITCH = "switch"  # ブレーキスイッチ。0/1 の二値のみ


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


# --------------------------------------------------------------------------
# 車両固有パラメータ
# --------------------------------------------------------------------------


class VehicleParams(ShasouModel):
    """車両固有パラメータ。CARLA ブリッジ / CAN デコーダのアダプタが変換に使う。

    Platform にネストされる区画であり、単独で配布されることはない。車種の
    識別は Platform.vehicle_type が唯一の正 (ここには持たない)。

    platform 定義は手書きされうるため、すべて optional。値が無いパラメータを
    必要とするアダプタは、その時点でエラーにする。
    """

    steering_gear_ratio: Optional[float] = Field(
        default=None, gt=0,
        description="ハンドル角→前輪実舵角の変換比 (実舵角 = ハンドル角 / ratio)。"
        "角度は rad・左転舵正",
    )
    max_steer_angle_rad: Optional[float] = Field(
        default=None, gt=0, le=math.pi,
        description="最大前輪実舵角 [rad]。CARLA 正規化 steer [-1,1] → rad 変換用",
    )
    speed_sign_rule: Optional[SpeedSignRule] = Field(
        default=None,
        description="ソース速度の符号規則。契約 (m/s・後退負) への変換方法",
    )
    brake_normalization: Optional[BrakeNormalization] = Field(
        default=None,
        description="pedals トピックの brake=1.0 の定義",
    )
    base_link_offset: Optional[Vector3] = Field(
        default=None,
        description="車両モデル原点→後軸中心のオフセット [m]。右手系",
    )


class Platform(ShasouModel):
    """platform 定義。sensor_rig (チャネル集合) + vehicle_type。"""

    platform_id: str = Field(description="platform ID (フォルダ名と一致)")
    vehicle_type: str
    sensor_rig: list[ChannelSpec] = Field(
        description="この platform のセンサ構成。実チャネル集合の正",
    )
    vehicle_params: Optional[VehicleParams] = Field(
        default=None,
        description="車両固有パラメータ。アダプタが変換に使う",
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
