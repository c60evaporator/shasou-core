"""calibration スキーマ (雛形)。

1 回の calibration は複数センサ分のエントリを含み、nuScenes 変換時にそれぞれが
calibrated_sensor レコードに展開される (1:N)。

このファイルは validation.py が参照する最小骨格のみ。CameraIntrinsics の歪み
係数や SensorExtrinsics の光学フレーム規約の詳細は CLI で肉付けする。
TODO(cli): CameraIntrinsics / SensorExtrinsics のフィールドを充足させる。
"""

from __future__ import annotations

from datetime import date

from pydantic import Field, field_validator

from ..constants import is_valid_channel_name
from .common import ShasouModel


class SensorCalibEntry(ShasouModel):
    """calibration 内の 1 センサ分。変換で 1 calibrated_sensor に展開される。"""

    channel: str
    # TODO(cli): intrinsics (CameraIntrinsics), extrinsics (SensorExtrinsics)

    @field_validator("channel")
    @classmethod
    def _valid_name(cls, v: str) -> str:
        if not is_valid_channel_name(v):
            raise ValueError(f"チャネル名が命名規約違反: {v!r}")
        return v


class CalibrationSet(ShasouModel):
    """1 回のキャリブレーション (calib_id で識別)。複数センサを含む。"""

    calib_id: str
    captured_at: date
    entries: list[SensorCalibEntry] = Field(
        description="各センサのキャリブ。1 エントリ = 1 calibrated_sensor",
    )

    def channel_names(self) -> set[str]:
        return {e.channel for e in self.entries}
