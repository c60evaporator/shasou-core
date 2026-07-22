import pytest

from shasou_core.schemas.calibration import (
    CalibrationSet,
    CameraIntrinsics,
    SensorCalibEntry,
    SensorExtrinsics,
)
from shasou_core.schemas.common import (
    DataSource,
    EgoPoseBackend,
    Modality,
    QuaternionXYZW,
    Vector3,
)
from shasou_core.schemas.manifest import DriveManifest
from shasou_core.schemas.platform import (
    CameraConfig,
    CameraIntrinsicsModel,
    ChannelSpec,
    Platform,
)
from shasou_core.schemas.vehicle import Vehicle
from shasou_core.validation import (
    Severity,
    validate_calibration_against_platform,
    validate_calibration_coverage,
    validate_drive,
    validate_manifest_against_platform,
    validate_observed_topics,
    validate_vehicle_consistency,
)


def _calib_entry(channel):
    """新契約 (extrinsics 必須・カメラは intrinsics 必須) を満たす最小 entry。"""
    intrinsics = None
    if channel.startswith("CAM_"):
        intrinsics = CameraIntrinsics(
            model=CameraIntrinsicsModel.PINHOLE_PLUMB_BOB,
            fx=1000.0, fy=1000.0, cx=800.0, cy=450.0,
            width=1600, height=900,
        )
    return SensorCalibEntry(
        channel=channel,
        extrinsics=SensorExtrinsics(
            translation=Vector3(x=0.0, y=0.0, z=0.0),
            rotation=QuaternionXYZW.identity(),
        ),
        intrinsics=intrinsics,
    )


def _platform(channels=(("CAM_FRONT", Modality.CAMERA), ("LIDAR_TOP", Modality.LIDAR))):
    return Platform(
        platform_id="platform_test",
        vehicle_type="lincoln",
        sensor_rig=[ChannelSpec(channel=c, modality=m) for c, m in channels],
    )


def _manifest(sensor_config=None, **overrides):
    if sensor_config is None:
        sensor_config = {
            "CAM_FRONT": "/sensing/cam_front/image_raw/compressed",
            "LIDAR_TOP": "/sensing/lidar_top/points",
        }
    data = dict(
        drive_id="2026-07-16_1030_v01_osaka",
        uuid="7f3a0000000000000000000000000000",
        source=DataSource.REAL,
        platform="platform_test",
        vehicle="v01",
        ego_pose_backend=EgoPoseBackend.PPK_INS,
        calib_id="calib_v001",
        date_captured="2026-07-16",
        location="osaka",
        recorder_version="v1.0.0",
        sensor_config=sensor_config,
    )
    data.update(overrides)
    return DriveManifest(**data)


def _carla_manifest(**overrides):
    data = dict(source=DataSource.CARLA, ego_pose_backend=EgoPoseBackend.CARLA_GT)
    data.update(overrides)
    return _manifest(**data)


# 規約どおりに収録された bag のトピック集合。名前空間は sensor_config と揃える
_COMMON_TOPICS = {
    "/sensing/cam_front/image_raw/compressed",
    "/sensing/cam_front/camera_info",
    "/sensing/lidar_top/points",
    "/sensing/imu",
    "/sensing/gnss_fix",
    "/sensing/events",
    "/sensing/tf_static",
    "/sensing/vehicle/drive_state",
    "/sensing/vehicle/pedals",
    "/sensing/vehicle/reverse",
    "/sensing/vehicle/handbrake",
}
_GT_TOPICS = {
    "/sensing/gt/ego_odom",
    "/sensing/gt/objects",
    "/sensing/gt/agent_plan",
    "/sensing/gt/depth_cam_front/image",
    "/clock",
}


def _observed(source=DataSource.REAL, drop=(), add=()):
    topics = set(_COMMON_TOPICS)
    if source == DataSource.CARLA:
        topics |= _GT_TOPICS
    return (topics - set(drop)) | set(add)


def _codes(result, severity):
    return {i.code for i in result.issues if i.severity == severity}


class TestManifestVsPlatform:
    def test_matching_channels_ok(self):
        r = validate_manifest_against_platform(_manifest(), _platform())
        assert r.ok

    def test_platform_id_mismatch_is_error(self):
        r = validate_manifest_against_platform(
            _manifest(platform="other"), _platform())
        assert not r.ok
        assert any(i.code == "platform_id_mismatch" for i in r.errors())

    def test_channel_not_in_rig_is_error(self):
        # RADAR_FRONT は命名規約 OK だが platform に無い -> ERROR
        r = validate_manifest_against_platform(
            _manifest(sensor_config={
                "CAM_FRONT": "/a", "LIDAR_TOP": "/b", "RADAR_FRONT": "/c"}),
            _platform())
        assert not r.ok
        assert any(i.code == "channel_not_in_rig" for i in r.errors())

    def test_missing_channel_is_warning_not_error(self):
        # sensor_rig の LIDAR_TOP がドライブに無い -> WARNING、ok は True
        r = validate_manifest_against_platform(
            _manifest(sensor_config={"CAM_FRONT": "/a"}), _platform())
        assert r.ok
        assert any(
            i.severity == Severity.WARNING and i.code == "channel_missing_in_drive"
            for i in r.issues
        )


class TestCalibrationCoverage:
    def _calib(self, channels=("CAM_FRONT", "LIDAR_TOP"), calib_id="calib_v001",
               vehicle="v01"):
        return CalibrationSet(
            calib_id=calib_id,
            vehicle=vehicle,
            captured_at="2026-07-01",
            entries=[_calib_entry(c) for c in channels],
        )

    def test_full_coverage_ok(self):
        r = validate_calibration_coverage(_manifest(), _platform(), self._calib())
        assert r.ok

    def test_missing_calibration_is_error(self):
        r = validate_calibration_coverage(
            _manifest(), _platform(), self._calib(channels=("CAM_FRONT",)))
        assert not r.ok
        assert any(i.code == "calibration_missing" for i in r.errors())

    def test_calib_id_mismatch_error(self):
        r = validate_calibration_coverage(
            _manifest(), _platform(), self._calib(calib_id="other"))
        assert any(i.code == "calib_id_mismatch" for i in r.errors())

    def test_calibration_vehicle_mismatch_error(self):
        # 他車両のキャリブを誤って参照した -> ERROR (個体固有の値を流用不可)
        r = validate_calibration_coverage(
            _manifest(vehicle="v01"), _platform(), self._calib(vehicle="v99"))
        assert not r.ok
        assert "calibration_vehicle_mismatch" in _codes(r, Severity.ERROR)


class TestObservedTopics:
    def test_declared_topic_absent_is_error(self):
        r = validate_observed_topics(
            _manifest(), observed_topic_names={"/sensing/cam_front/image_raw/compressed"})
        # LIDAR_TOP のトピックが観測されていない
        assert not r.ok
        assert any(i.code == "declared_topic_absent" for i in r.errors())

    def test_all_present_ok(self):
        r = validate_observed_topics(_manifest(), observed_topic_names=_observed())
        assert r.ok
        assert not r.issues

    def test_carla_all_present_ok(self):
        r = validate_observed_topics(
            _carla_manifest(), observed_topic_names=_observed(DataSource.CARLA))
        assert r.ok
        assert not r.issues

    def test_carla_missing_core_gt_is_error(self):
        r = validate_observed_topics(
            _carla_manifest(),
            observed_topic_names=_observed(
                DataSource.CARLA, drop=("/sensing/gt/objects",)))
        assert not r.ok
        assert "gt_topic_absent" in _codes(r, Severity.ERROR)

    def test_carla_missing_clock_is_error(self):
        r = validate_observed_topics(
            _carla_manifest(),
            observed_topic_names=_observed(DataSource.CARLA, drop=("/clock",)))
        assert not r.ok
        assert "sim_topic_absent" in _codes(r, Severity.ERROR)

    def test_carla_missing_gt_depth_is_warning(self):
        # 中核 gt と違い、深度は一部カメラのみ収録する運用がありうる
        r = validate_observed_topics(
            _carla_manifest(),
            observed_topic_names=_observed(
                DataSource.CARLA, drop=("/sensing/gt/depth_cam_front/image",)))
        assert r.ok
        assert "gt_depth_topic_absent" in _codes(r, Severity.WARNING)

    def test_missing_drive_state_is_error(self):
        # E2E 学習の行動ラベル。欠けるとドライブが学習に使えない
        r = validate_observed_topics(
            _manifest(),
            observed_topic_names=_observed(drop=("/sensing/vehicle/drive_state",)))
        assert not r.ok
        assert "vehicle_topic_absent" in _codes(r, Severity.ERROR)

    def test_missing_handbrake_is_warning(self):
        # 補助フラグなので取り込みは通す
        r = validate_observed_topics(
            _manifest(),
            observed_topic_names=_observed(drop=("/sensing/vehicle/handbrake",)))
        assert r.ok
        assert "vehicle_aux_topic_absent" in _codes(r, Severity.WARNING)

    def test_missing_camera_info_is_warning(self):
        r = validate_observed_topics(
            _manifest(),
            observed_topic_names=_observed(drop=("/sensing/cam_front/camera_info",)))
        assert r.ok
        assert "sensor_topic_absent" in _codes(r, Severity.WARNING)

    def test_real_with_gt_topic_is_warning(self):
        # 実車データに特権情報の混入は異常だが、取り込み自体は可能
        r = validate_observed_topics(
            _manifest(), observed_topic_names=_observed(add=("/sensing/gt/ego_odom",)))
        assert r.ok
        assert "unexpected_topic_for_source" in _codes(r, Severity.WARNING)

    def test_real_with_clock_is_warning(self):
        r = validate_observed_topics(
            _manifest(), observed_topic_names=_observed(add=("/clock",)))
        assert r.ok
        assert "unexpected_topic_for_source" in _codes(r, Severity.WARNING)


class TestCalibrationVsPlatform:
    """ChannelSpec (構成の宣言) と CameraIntrinsics (実測) の整合。"""

    def _platform_with_camera(self, **camera_kwargs):
        data = dict(
            intrinsics_model=CameraIntrinsicsModel.PINHOLE_PLUMB_BOB,
            width_px=1600, height_px=900,
        )
        data.update(camera_kwargs)
        return Platform(
            platform_id="platform_test",
            vehicle_type="lincoln",
            sensor_rig=[
                ChannelSpec(
                    channel="CAM_FRONT", modality=Modality.CAMERA,
                    camera=CameraConfig(**data),
                ),
                ChannelSpec(channel="LIDAR_TOP", modality=Modality.LIDAR),
            ],
        )

    def _calib(self):
        return CalibrationSet(
            calib_id="calib_v001", vehicle="v01", captured_at="2026-07-01",
            entries=[_calib_entry(c) for c in ("CAM_FRONT", "LIDAR_TOP")])

    def test_matching_declaration_ok(self):
        # _calib_entry は plumb_bob / 1600x900 で作られる
        r = validate_calibration_against_platform(
            self._platform_with_camera(), self._calib())
        assert r.ok
        assert not r.issues

    def test_intrinsics_model_mismatch_is_error(self):
        r = validate_calibration_against_platform(
            self._platform_with_camera(
                intrinsics_model=CameraIntrinsicsModel.FISHEYE_EQUIDISTANT),
            self._calib())
        assert not r.ok
        assert "intrinsics_model_mismatch" in _codes(r, Severity.ERROR)

    def test_resolution_mismatch_is_warning(self):
        # 公称と実測のズレは運用上ありうるので取り込みは通す
        r = validate_calibration_against_platform(
            self._platform_with_camera(width_px=1920, height_px=1080),
            self._calib())
        assert r.ok
        assert "resolution_mismatch" in _codes(r, Severity.WARNING)

    def test_undeclared_fields_are_not_compared(self):
        # 宣言側が未記入なら照合しない (手書き platform 定義を圧迫しない)
        r = validate_calibration_against_platform(
            self._platform_with_camera(intrinsics_model=None,
                                       width_px=None, height_px=None),
            self._calib())
        assert not r.issues


class TestVehicleConsistency:
    def _vehicle(self, **overrides):
        data = dict(vehicle_id="v01", platform_id="platform_test")
        data.update(overrides)
        return Vehicle(**data)

    def test_matching_ok(self):
        r = validate_vehicle_consistency(_manifest(), self._vehicle())
        assert r.ok
        assert not r.issues

    def test_platform_mismatch_is_error(self):
        r = validate_vehicle_consistency(
            _manifest(), self._vehicle(platform_id="other_platform"))
        assert not r.ok
        assert "vehicle_platform_mismatch" in _codes(r, Severity.ERROR)

    def test_vehicle_id_mismatch_is_error(self):
        r = validate_vehicle_consistency(
            _manifest(vehicle="v01"), self._vehicle(vehicle_id="v99"))
        assert not r.ok
        assert "vehicle_id_mismatch" in _codes(r, Severity.ERROR)


class TestValidateDrive:
    def test_combined_ok(self):
        calib = CalibrationSet(
            calib_id="calib_v001", vehicle="v01", captured_at="2026-07-01",
            entries=[_calib_entry(c) for c in ("CAM_FRONT", "LIDAR_TOP")])
        r = validate_drive(
            _manifest(), _platform(), calibration=calib,
            observed_topic_names=_observed(),
            vehicle=Vehicle(vehicle_id="v01", platform_id="platform_test"))
        assert r.ok

    def test_partial_acceptance_shape(self):
        # ERROR と WARNING が混在しても issues に両方揃う (部分受理の材料)
        r = validate_drive(
            _manifest(platform="wrong", sensor_config={"CAM_FRONT": "/a"}),
            _platform())
        severities = {i.severity for i in r.issues}
        assert Severity.ERROR in severities
        assert not r.ok
