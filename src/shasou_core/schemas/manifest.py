"""DriveManifest スキーマ。

manifest.yaml はドライブの自己記述メタデータで、nuScenes の log テーブル等の
生成元となる。recorder が走行ごとに生成し、studio が取り込み時に読む。
manifest は自己完結する (ディレクトリから自明な情報も冗長に持つ)。
"""

from __future__ import annotations

from datetime import date
from enum import Enum

from pydantic import Field, field_validator, model_validator

from ..constants import is_valid_channel_name
from ..version import SCHEMA_VERSION, major
from .common import DataSource, EgoPoseBackend, ShasouModel, Token


class DriveStatus(str, Enum):
    """ドライブの処理到達段階 (所在ではなく段階)。

    recorder 側 catalog が管理するのは verified まで。imported 以降は
    studio が Raw 層取り込み時に catalog へ書き戻す。
    """

    RECORDED = "recorded"        # 収録完了 (車上 SSD)
    TRANSFERRED = "transferred"  # NAS へコピー完了 (検証前)
    VERIFIED = "verified"        # チェックサム照合済み (NAS 上で健全)
    IMPORTED = "imported"        # studio が Raw 層に取り込んだ


class ArchiveStatus(str, Enum):
    """S3 アーカイブ状態。status とは独立の軸。"""

    NONE = "none"          # NAS のみ
    ARCHIVED = "archived"  # S3 標準ストレージへ退避
    GLACIER = "glacier"    # Glacier Deep Archive へ退避


class DriveManifest(ShasouModel):
    """1 ドライブの自己記述メタデータ (manifest.yaml)。"""

    # --- 識別 ---
    drive_id: str = Field(description="人間可読 ID。日付_時刻_車両_場所")
    uuid: str = Field(description="機械的一意性のための UUID")
    schema_version: str = Field(
        default=SCHEMA_VERSION,
        description="書き込み時の shasou-core スキーマ版。読み手は MAJOR 一致を要求",
    )

    # --- 出自 ---
    source: DataSource
    platform: str = Field(description="platform ID (フォルダ名と一致)")
    vehicle: str
    ego_pose_backend: EgoPoseBackend

    # --- キャリブ参照 ---
    calib_id: str = Field(description="calibrations/ 直下の 1 フォルダを一意に指す")

    # --- nuScenes log 用メタ ---
    date_captured: date
    location: str = Field(description="→ nuScenes log.location")
    driver: str | None = None
    weather: str | None = Field(default=None, description="→ scene.description の素材")

    # --- 収録環境 ---
    recorder_version: str

    # --- センサ ⇔ トピック対応 (実センサのみ。gt 系は含めない) ---
    sensor_config: dict[str, str] = Field(
        description="正規チャネル名 -> 実トピック名。RADAR 含む",
    )

    # --- 状態 ---
    status: DriveStatus = DriveStatus.RECORDED
    archive_status: ArchiveStatus = ArchiveStatus.NONE

    @field_validator("sensor_config")
    @classmethod
    def _valid_channel_names(cls, v: dict[str, str]) -> dict[str, str]:
        # manifest 単体では命名規約のみ検証する。実際のチャネル集合が platform の
        # sensor_rig と一致するかの照合は validation.py (横断検証) の責務。
        malformed = sorted(ch for ch in v if not is_valid_channel_name(ch))
        if malformed:
            raise ValueError(
                f"sensor_config のチャネル名が命名規約に違反: {malformed}. "
                "CAM_/LIDAR_/RADAR_ で始まり大文字英数字とアンダースコアのみ許容"
            )
        return v

    @model_validator(mode="after")
    def _carla_uses_gt_backend(self) -> "DriveManifest":
        # CARLA なら真値バックエンド、実車なら真値以外、という緩い整合チェック
        if self.source == DataSource.CARLA and self.ego_pose_backend != EgoPoseBackend.CARLA_GT:
            raise ValueError("source=carla では ego_pose_backend=carla-gt を推奨/要求")
        if self.source == DataSource.REAL and self.ego_pose_backend == EgoPoseBackend.CARLA_GT:
            raise ValueError("source=real で carla-gt バックエンドは使用不可")
        return self

    def is_schema_compatible(self, reader_version: str = SCHEMA_VERSION) -> bool:
        """読み手のスキーマ版と MAJOR 一致するか。"""
        return major(self.schema_version) == major(reader_version)
