"""横断検証 (cross-cutting validation)。

個々のスキーマの field_validator は「そのモデル単体で閉じる」検証を担う。
このモジュールは、複数のスキーマ/成果物をまたいで初めて判定できる整合性を
担う。recorder の起動時検証と studio の取り込み時検証が共通して使う。

主な検証:
1. manifest.sensor_config のチャネル集合 == platform.sensor_rig のチャネル集合
   (命名規約は manifest 単体で済むが、「実在するか」は platform 照合が必要)
2. manifest.calib_id が指す CalibrationSet が platform の全センサを網羅するか
3. manifest.platform が Platform.platform_id と一致するか
4. (bag 検証用) 実トピック集合が source 別トピック契約を満たすか

設計方針
--------
各検証関数は「例外を投げる」のではなく Issue のリストを返す。呼び出し側が
warning/error を選別し、部分受理 (以前議論した「一部棄却・残り取り込み」) を
実装できるようにするため。重大度は Severity で表す。
"""

from __future__ import annotations

from dataclasses import dataclass, field
from enum import Enum

from .constants import channel_modality
from .schemas.calibration import CalibrationSet
from .schemas.manifest import DriveManifest
from .schemas.platform import Platform


class Severity(str, Enum):
    ERROR = "error"      # 取り込み/収録を止めるべき
    WARNING = "warning"  # 記録するが続行可
    INFO = "info"


@dataclass
class Issue:
    severity: Severity
    code: str            # 機械可読な識別子 (例: "channel_mismatch")
    message: str
    context: dict = field(default_factory=dict)


@dataclass
class ValidationResult:
    issues: list[Issue] = field(default_factory=list)

    def add(self, severity: Severity, code: str, message: str, **context) -> None:
        self.issues.append(Issue(severity, code, message, context))

    @property
    def ok(self) -> bool:
        """ERROR が 1 つも無ければ True (WARNING は許容)。"""
        return not any(i.severity == Severity.ERROR for i in self.issues)

    def errors(self) -> list[Issue]:
        return [i for i in self.issues if i.severity == Severity.ERROR]

    def merge(self, other: "ValidationResult") -> "ValidationResult":
        self.issues.extend(other.issues)
        return self


# --------------------------------------------------------------------------
# 1. manifest x platform: チャネル集合の照合
# --------------------------------------------------------------------------


def validate_manifest_against_platform(
    manifest: DriveManifest, platform: Platform
) -> ValidationResult:
    """manifest の sensor_config が platform の sensor_rig と整合するか。

    - platform_id 不一致 -> ERROR
    - sensor_config にあって sensor_rig に無いチャネル -> ERROR
      (未定義センサのデータ。platform 定義漏れか収録ミス)
    - sensor_rig にあって sensor_config に無いチャネル -> WARNING
      (そのドライブで一部センサが欠測。収録は成立しうる)
    """
    result = ValidationResult()

    if manifest.platform != platform.platform_id:
        result.add(
            Severity.ERROR, "platform_id_mismatch",
            f"manifest.platform ({manifest.platform}) != "
            f"platform.platform_id ({platform.platform_id})",
            manifest_platform=manifest.platform,
            platform_id=platform.platform_id,
        )

    manifest_channels = set(manifest.sensor_config)
    rig_channels = platform.channel_names()

    for ch in sorted(manifest_channels - rig_channels):
        result.add(
            Severity.ERROR, "channel_not_in_rig",
            f"sensor_config のチャネル {ch} が platform の sensor_rig に無い",
            channel=ch,
        )
    for ch in sorted(rig_channels - manifest_channels):
        result.add(
            Severity.WARNING, "channel_missing_in_drive",
            f"sensor_rig のチャネル {ch} がこのドライブの sensor_config に無い "
            "(欠測の可能性)",
            channel=ch,
        )
    return result


# --------------------------------------------------------------------------
# 2. manifest x calibration: キャリブのセンサ網羅性
# --------------------------------------------------------------------------


def validate_calibration_coverage(
    manifest: DriveManifest, platform: Platform, calibration: CalibrationSet
) -> ValidationResult:
    """calib_id が指す CalibrationSet が platform の全センサを網羅するか。

    - calib_id 不一致 -> ERROR
    - platform の sensor_rig にあって calibration に無いチャネル -> ERROR
      (キャリブ欠落。nuScenes 変換時に calibrated_sensor を作れない)
    - calibration にあって sensor_rig に無いチャネル -> WARNING
    """
    result = ValidationResult()

    if manifest.calib_id != calibration.calib_id:
        result.add(
            Severity.ERROR, "calib_id_mismatch",
            f"manifest.calib_id ({manifest.calib_id}) != "
            f"calibration.calib_id ({calibration.calib_id})",
        )

    rig_channels = platform.channel_names()
    calib_channels = calibration.channel_names()

    for ch in sorted(rig_channels - calib_channels):
        result.add(
            Severity.ERROR, "calibration_missing",
            f"platform センサ {ch} のキャリブが calib_id={calibration.calib_id} に無い",
            channel=ch,
        )
    for ch in sorted(calib_channels - rig_channels):
        result.add(
            Severity.WARNING, "calibration_extra",
            f"キャリブに platform 外のチャネル {ch} が含まれる",
            channel=ch,
        )
    return result


# --------------------------------------------------------------------------
# 3. bag トピック検証 (recorder 起動時 / studio 取り込み時)
# --------------------------------------------------------------------------


def validate_observed_topics(
    manifest: DriveManifest,
    observed_topic_names: set[str],
) -> ValidationResult:
    """実際に bag に存在したトピック名が sensor_config と整合するか。

    sensor_config で宣言したトピックが bag に無ければ ERROR (収録漏れ)。
    TODO(cli): source 別トピック契約 (topics.contracts_for_source) と突き合わせ、
    gt 系や車両状態トピックの過不足も検証する。ここでは sensor_config で宣言した
    センサトピックの存在確認のみを代表実装として置く。
    """
    result = ValidationResult()
    declared = set(manifest.sensor_config.values())
    for topic in sorted(declared - observed_topic_names):
        result.add(
            Severity.ERROR, "declared_topic_absent",
            f"sensor_config で宣言したトピック {topic} が bag に存在しない",
            topic=topic,
        )
    return result


# --------------------------------------------------------------------------
# 統合エントリポイント
# --------------------------------------------------------------------------


def validate_drive(
    manifest: DriveManifest,
    platform: Platform,
    calibration: CalibrationSet | None = None,
    observed_topic_names: set[str] | None = None,
) -> ValidationResult:
    """1 ドライブの取り込み前検証をまとめて実行する。

    studio の取り込み時に呼ぶ想定。calibration / observed_topic_names が
    与えられれば該当検証も回す。ok が False (ERROR あり) なら取り込みを保留し、
    issues を記録する (以前議論した部分受理はこの結果を見て呼び出し側が判断)。
    """
    result = validate_manifest_against_platform(manifest, platform)
    if calibration is not None:
        result.merge(validate_calibration_coverage(manifest, platform, calibration))
    if observed_topic_names is not None:
        result.merge(validate_observed_topics(manifest, observed_topic_names))
    return result
