"""platform 定義スキーマ (雛形)。

platform は「学習データとして一体利用できる」単位で、センサ構成 (sensor_rig)
と車種 (vehicle_type) が一致するデータをグルーピングする。studio が編集元
(source of truth) で、recorder は同期して使う。

このファイルは validation.py が参照する最小骨格のみを定義する。VehicleParams
の詳細フィールド (ステアリングギア比・最大舵角・ブレーキ正規化定義・base_link
オフセット等) や ChannelSpec の外部パラメータ型は CLI で肉付けする。
TODO(cli): VehicleParams / ChannelSpec のフィールドを充足させる。
"""

from __future__ import annotations

from pydantic import Field, field_validator

from ..constants import channel_modality, is_valid_channel_name
from .common import Modality, ShasouModel


class ChannelSpec(ShasouModel):
    """platform の sensor_rig を構成する 1 チャネルの定義。"""

    channel: str = Field(description="正規チャネル名 (CAM_FRONT 等)")
    modality: Modality
    # TODO(cli): 外部パラメータ・内部パラメータの型参照、解像度、FOV 等

    @field_validator("channel")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not is_valid_channel_name(v):
            raise ValueError(f"チャネル名が命名規約違反: {v!r}")
        return v


class VehicleParams(ShasouModel):
    """車両固有パラメータ (雛形)。CARLA/実車のアダプタが変換に使う。"""

    # TODO(cli): steering_gear_ratio, max_steer_angle_rad, speed_sign_rule,
    #            brake_normalization, base_link_offset 等
    vehicle_type: str


class Platform(ShasouModel):
    """platform 定義。sensor_rig (チャネル集合) + vehicle_type。"""

    platform_id: str = Field(description="platform ID (フォルダ名と一致)")
    vehicle_type: str
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
