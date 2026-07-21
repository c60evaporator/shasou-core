"""calibration スキーマ。

1 回の calibration は複数センサ分のエントリを含み、nuScenes 変換時にそれぞれが
calibrated_sensor レコードに展開される (1:N)。calibrated_sensor token は
derived_token(calib_id, channel) で決定的に生成し、再エクスポートで安定させる。

platform.py との責務分担: ChannelSpec は構成上の宣言 (公称値・期待する
内部パラメータモデルの型参照) を持ち、このファイルはキャリブレーション 1 回
ごとの *実測値* を持つ。宣言と実測の整合照合は validation.py の責務。
"""

from __future__ import annotations

from datetime import date
from typing import Optional

from pydantic import Field, field_validator, model_validator

from ..constants import channel_modality, is_valid_channel_name
from .common import Pose, ShasouModel, derived_token
from .platform import CameraIntrinsicsModel

# モデル別に許容する歪み係数の個数。0 は「無歪み」(CARLA の理想ピンホール等)
_DISTORTION_LENGTHS = {
    CameraIntrinsicsModel.PINHOLE_PLUMB_BOB: (0, 5),  # k1, k2, p1, p2, k3
    CameraIntrinsicsModel.FISHEYE_EQUIDISTANT: (0, 4),  # k1..k4
}


class CameraIntrinsics(ShasouModel):
    """カメラ内部パラメータの実測値。

    実車は歪みあり raw を前提とし、ここには実測パラメータをそのまま持つ。
    歪み補正 (undistort) と nuScenes camera_intrinsic への変換は下流
    (エクスポータ) の責務で、生値に焼き込まない。
    """

    model: CameraIntrinsicsModel = Field(
        description="内部パラメータモデル。ChannelSpec の期待宣言と同一語彙",
    )
    fx: float = Field(gt=0, description="焦点距離 x [px]")
    fy: float = Field(gt=0, description="焦点距離 y [px]")
    cx: float = Field(description="主点 x [px]")
    cy: float = Field(description="主点 y [px]")
    width: int = Field(ge=1, description="このキャリブが有効な画像幅 [px]")
    height: int = Field(ge=1, description="このキャリブが有効な画像高さ [px]")
    distortion: list[float] = Field(
        default_factory=list,
        description="歪み係数 (モデル別の並び)。空は無歪み",
    )

    @model_validator(mode="after")
    def _distortion_length(self) -> "CameraIntrinsics":
        allowed = _DISTORTION_LENGTHS[self.model]
        if len(self.distortion) not in allowed:
            raise ValueError(
                f"{self.model.value} の歪み係数は {allowed} 個のいずれか "
                f"(実際: {len(self.distortion)} 個)"
            )
        return self

    def as_matrix(self) -> list[list[float]]:
        """3x3 カメラ行列 K (row-major)。エクスポータの camera_intrinsic 用。"""
        return [
            [self.fx, 0.0, self.cx],
            [0.0, self.fy, self.cy],
            [0.0, 0.0, 1.0],
        ]


class SensorExtrinsics(Pose):
    """base_link 基準のセンサ実測搭載位置姿勢。

    - translation: base_link → センサフレームの平行移動 [m]
    - rotation: 単位クォータニオン、ROS 順 (x, y, z, w)。nuScenes の
      (w, x, y, z) への並び替えは下流の責務でここでは行わない
    - カメラは光学フレーム規約 (Z前 / X右 / Y下) に従う値を持つ

    設計搭載位置 (公称値) は platform.py の ChannelSpec.nominal_mount 側。
    """


class SensorCalibEntry(ShasouModel):
    """calibration 内の 1 センサ分。変換で 1 calibrated_sensor に展開される。"""

    channel: str
    extrinsics: SensorExtrinsics = Field(
        description="base_link 基準の実測搭載位置姿勢 (全センサ共通)",
    )
    intrinsics: Optional[CameraIntrinsics] = Field(
        default=None,
        description="カメラ内部パラメータの実測値。カメラチャネルのみ",
    )

    @field_validator("channel")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not is_valid_channel_name(v):
            raise ValueError(f"チャネル名が命名規約違反: {v!r}")
        return v

    @model_validator(mode="after")
    def _intrinsics_matches_modality(self) -> "SensorCalibEntry":
        modality = channel_modality(self.channel)
        if modality == "camera" and self.intrinsics is None:
            raise ValueError(
                f"{self.channel}: カメラチャネルには intrinsics が必須 "
                "(camera_intrinsic に展開できない)"
            )
        if modality != "camera" and self.intrinsics is not None:
            raise ValueError(
                f"{self.channel}: intrinsics はカメラチャネルのみ "
                f"(modality: {modality})"
            )
        return self


class CalibrationSet(ShasouModel):
    """1 回のキャリブレーション (calib_id で識別)。複数センサを含む。"""

    calib_id: str
    captured_at: date
    entries: list[SensorCalibEntry] = Field(
        description="各センサのキャリブ。1 エントリ = 1 calibrated_sensor",
    )

    def channel_names(self) -> set[str]:
        return {e.channel for e in self.entries}

    def calibrated_sensor_token(self, channel: str) -> str:
        """channel の calibrated_sensor token を決定的に導出する (uuid5)。

        同じ calib_id + channel からは常に同じ token が得られ、Scene 切り出しの
        変更や再エクスポートで安定する。entries に無い channel は KeyError
        (存在しない calibrated_sensor の token は無意味)。
        """
        if channel not in self.channel_names():
            raise KeyError(f"channel {channel!r} はこの calibration に含まれない")
        return derived_token(self.calib_id, channel)

    def calibrated_sensor_tokens(self) -> dict[str, str]:
        """全 entry の {channel: token}。1 CalibrationSet → N calibrated_sensor。"""
        return {
            e.channel: derived_token(self.calib_id, e.channel) for e in self.entries
        }
