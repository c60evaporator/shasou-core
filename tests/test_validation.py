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
from shasou_core.schemas.platform import CameraIntrinsicsModel, ChannelSpec, Platform
from shasou_core.validation import (
    Severity,
    validate_calibration_coverage,
    validate_drive,
    validate_manifest_against_platform,
    validate_observed_topics,
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
    def _calib(self, channels=("CAM_FRONT", "LIDAR_TOP"), calib_id="calib_v001"):
        return CalibrationSet(
            calib_id=calib_id,
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


class TestObservedTopics:
    def test_declared_topic_absent_is_error(self):
        r = validate_observed_topics(
            _manifest(), observed_topic_names={"/sensing/cam_front/image_raw/compressed"})
        # LIDAR_TOP のトピックが観測されていない
        assert not r.ok
        assert any(i.code == "declared_topic_absent" for i in r.errors())

    def test_all_present_ok(self):
        r = validate_observed_topics(
            _manifest(),
            observed_topic_names={
                "/sensing/cam_front/image_raw/compressed",
                "/sensing/lidar_top/points",
            })
        assert r.ok


class TestValidateDrive:
    def test_combined_ok(self):
        calib = CalibrationSet(
            calib_id="calib_v001", captured_at="2026-07-01",
            entries=[_calib_entry(c) for c in ("CAM_FRONT", "LIDAR_TOP")])
        r = validate_drive(
            _manifest(), _platform(), calibration=calib,
            observed_topic_names={
                "/sensing/cam_front/image_raw/compressed",
                "/sensing/lidar_top/points",
            })
        assert r.ok

    def test_partial_acceptance_shape(self):
        # ERROR と WARNING が混在しても issues に両方揃う (部分受理の材料)
        r = validate_drive(
            _manifest(platform="wrong", sensor_config={"CAM_FRONT": "/a"}),
            _platform())
        severities = {i.severity for i in r.issues}
        assert Severity.ERROR in severities
        assert not r.ok
