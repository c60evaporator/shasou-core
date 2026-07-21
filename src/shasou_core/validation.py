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
5. platform の構成宣言 (ChannelSpec) と calibration の実測値が整合するか

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
from .schemas.topics import (
    ALL_CONTRACTS,
    TopicContract,
    TopicRole,
    contracts_for_source,
    resolve_topic_name,
)


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


# 中核の特権情報。CARLA では trajectory / sample_annotation の源泉であり、
# 欠けるとドライブが変換できない。gt_depth は補助的な深度ラベルなので別扱い。
_CORE_GT_KEYS = frozenset({"gt_ego_odom", "gt_objects", "gt_agent_plan"})

# E2E 学習の行動ラベル (steering / throttle / brake)。欠けると学習に使えない。
# reverse / handbrake は補助フラグなので別扱い。
_REQUIRED_VEHICLE_KEYS = frozenset({"vehicle_drive_state", "vehicle_pedals"})


def _expected_suffixes(channel: str, contract: TopicContract) -> set[str]:
    """契約が固定する期待トピック名の「末尾セグメント」候補を返す。

    名前空間はデプロイ依存 (sensor_config の実名が正) なので決め打ちせず、
    規約が固定する末尾のみを見る。resolve_topic_name を名前空間なしで呼ぶと
    末尾そのものが得られる (例: "/gt/depth_cam_front/image", "/clock")。
    非 per_channel の論理キーは §5 の名前空間形式 ("/vehicle/drive_state") でも
    書かれうるため、最初の "_" を "/" に置換した変種も候補に加える。
    """
    suffixes = {resolve_topic_name("", channel, contract)}
    if not contract.per_channel and "_" in contract.key:
        suffixes.add("/" + contract.key.replace("_", "/", 1))
    return suffixes


def _is_observed(observed_topic_names: set[str], suffixes: set[str]) -> bool:
    return any(t.endswith(s) for t in observed_topic_names for s in suffixes)


def _channels_for(manifest: DriveManifest, contract: TopicContract) -> set[str]:
    """per_channel 契約を展開する対象チャネル (sensor_config を modality で絞る)。"""
    return {
        ch for ch in manifest.sensor_config
        if channel_modality(ch) == contract.modality.value
    }


def _absence_issue(contract: TopicContract) -> tuple[Severity, str]:
    """契約が満たされなかったときの重大度と Issue code。

    「宣言あって実体無し=ERROR、余剰=WARNING」の非対称に加え、契約側が存在を
    要求するトピックのうち、欠けるとドライブが使い物にならないものを ERROR、
    構成・運用で変わりうるものを WARNING とする。
    """
    if contract.key in _CORE_GT_KEYS:
        return Severity.ERROR, "gt_topic_absent"
    if contract.role == TopicRole.GROUND_TRUTH:
        # gt_depth。一部カメラのみ収録する運用がありうる
        return Severity.WARNING, "gt_depth_topic_absent"
    if contract.role == TopicRole.SIM_ONLY:
        return Severity.ERROR, "sim_topic_absent"
    if contract.key in _REQUIRED_VEHICLE_KEYS:
        return Severity.ERROR, "vehicle_topic_absent"
    if contract.role == TopicRole.VEHICLE:
        return Severity.WARNING, "vehicle_aux_topic_absent"
    # imu / gnss / events / tf_static / camera_info。sensor_config は
    # CAM_/LIDAR_/RADAR_ しか宣言できず、rig に実在するか判定できない
    return Severity.WARNING, "sensor_topic_absent"


def validate_observed_topics(
    manifest: DriveManifest,
    observed_topic_names: set[str],
) -> ValidationResult:
    """実際に bag に存在したトピック名が sensor_config と契約に整合するか。

    1. sensor_config で宣言したトピックが bag に無ければ ERROR (収録漏れ)
    2. source 別トピック契約 (contracts_for_source) の過不足。per_channel の
       契約は sensor_config のチャネルを contract.modality で絞って展開する。
       gt_depth は sensor_config に depth チャネルが無い (RGB と光学フレームを
       共有する派生 GT) ため、カメラチャネルに対して展開する
    3. REAL に gt / clock が混入していれば WARNING (異常だが取り込みは可能)
    """
    result = ValidationResult()
    declared = set(manifest.sensor_config.values())
    for topic in sorted(declared - observed_topic_names):
        result.add(
            Severity.ERROR, "declared_topic_absent",
            f"sensor_config で宣言したトピック {topic} が bag に存在しない",
            topic=topic,
        )

    for contract in contracts_for_source(manifest.source):
        severity, code = _absence_issue(contract)
        if contract.per_channel:
            for channel in sorted(_channels_for(manifest, contract)):
                if _is_observed(
                    observed_topic_names, _expected_suffixes(channel, contract)
                ):
                    continue
                result.add(
                    severity, code,
                    f"契約 {contract.key} のトピックがチャネル {channel} 分だけ "
                    "bag に存在しない",
                    contract=contract.key, channel=channel,
                )
        elif not _is_observed(observed_topic_names, _expected_suffixes("", contract)):
            result.add(
                severity, code,
                f"source={manifest.source.value} で期待されるトピック "
                f"{contract.key} が bag に存在しない",
                contract=contract.key,
            )

    allowed_keys = {c.key for c in contracts_for_source(manifest.source)}
    for contract in ALL_CONTRACTS:
        if contract.key in allowed_keys:
            continue
        channels = (
            sorted(_channels_for(manifest, contract)) if contract.per_channel else [""]
        )
        for channel in channels:
            if not _is_observed(
                observed_topic_names, _expected_suffixes(channel, contract)
            ):
                continue
            result.add(
                Severity.WARNING, "unexpected_topic_for_source",
                f"source={manifest.source.value} に存在しないはずのトピック "
                f"{contract.key} が bag にある (role={contract.role.value})",
                contract=contract.key, channel=channel,
            )
    return result


# --------------------------------------------------------------------------
# 4. platform x calibration: 宣言 (構成) と実測の整合
# --------------------------------------------------------------------------


def validate_calibration_against_platform(
    platform: Platform, calibration: CalibrationSet
) -> ValidationResult:
    """ChannelSpec の構成宣言と CalibrationSet の実測値が整合するか。

    - 期待する内部パラメータモデルと実測モデルの不一致 -> ERROR
      (宣言と別モデルでキャリブされている。歪み補正が破綻する)
    - 公称解像度と実測解像度の不一致 -> WARNING
      (運用上ありうるズレ。実測側が正だが宣言の更新漏れを知らせる)

    宣言側が未記入 (None) の項目は照合しない。entry 自体の欠落は
    validate_calibration_coverage の責務なのでここでは重複させない。
    TODO(next): nominal_mount (設計搭載位置) と extrinsics (実測) の乖離検証。
    許容閾値の設計 (並進 [m] / 回転 [rad] をどこで切るか) が必要。
    """
    result = ValidationResult()
    entries = {e.channel: e for e in calibration.entries}

    for spec in platform.sensor_rig:
        entry = entries.get(spec.channel)
        if spec.camera is None or entry is None or entry.intrinsics is None:
            continue

        declared_model = spec.camera.intrinsics_model
        if declared_model is not None and declared_model != entry.intrinsics.model:
            result.add(
                Severity.ERROR, "intrinsics_model_mismatch",
                f"{spec.channel}: platform の宣言モデル ({declared_model.value}) と "
                f"キャリブ実測モデル ({entry.intrinsics.model.value}) が不一致",
                channel=spec.channel,
                declared=declared_model.value,
                measured=entry.intrinsics.model.value,
            )

        declared_size = (spec.camera.width_px, spec.camera.height_px)
        measured_size = (entry.intrinsics.width, entry.intrinsics.height)
        if declared_size[0] is not None and declared_size != measured_size:
            result.add(
                Severity.WARNING, "resolution_mismatch",
                f"{spec.channel}: platform の公称解像度 {declared_size[0]}x"
                f"{declared_size[1]} とキャリブ実測 {measured_size[0]}x"
                f"{measured_size[1]} が不一致",
                channel=spec.channel,
                declared_width=declared_size[0], declared_height=declared_size[1],
                measured_width=measured_size[0], measured_height=measured_size[1],
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
        result.merge(validate_calibration_against_platform(platform, calibration))
    if observed_topic_names is not None:
        result.merge(validate_observed_topics(manifest, observed_topic_names))
    return result
