import pytest
from pydantic import ValidationError

from shasou_core.schemas.common import DataSource
from shasou_core.schemas.manifest import (
    ArchiveStatus,
    DriveManifest,
    DriveStatus,
    EgoPoseBackend,
)
from shasou_core.schemas.topics import (
    PEDAL_JOINT_NAMES,
    TopicRole,
    contracts_for_source,
    resolve_topic_name,
    CAMERA_IMAGE,
    GT_DEPTH_IMAGE,
    RADAR_POINTS,
)


class TestTopicSets:
    def test_carla_includes_gt_excludes_nothing_real_only(self):
        contracts = contracts_for_source(DataSource.CARLA)
        roles = {c.role for c in contracts}
        assert TopicRole.GROUND_TRUTH in roles
        assert TopicRole.SIM_ONLY in roles
        assert TopicRole.REAL_ONLY not in roles

    def test_real_excludes_gt_and_sim(self):
        contracts = contracts_for_source(DataSource.REAL)
        roles = {c.role for c in contracts}
        assert TopicRole.GROUND_TRUTH not in roles
        assert TopicRole.SIM_ONLY not in roles

    def test_radar_required_fields(self):
        required = [f.name for f in RADAR_POINTS.point_fields if f.required]
        assert "velocity_radial" in required
        # rcs/dynprop は optional
        opt = [f.name for f in RADAR_POINTS.point_fields if not f.required]
        assert "rcs" in opt


class TestTopicNames:
    def test_camera_image_name(self):
        n = resolve_topic_name("/shasou", "CAM_FRONT", CAMERA_IMAGE)
        assert n == "/shasou/cam_front/image_raw/compressed"

    def test_depth_goes_under_gt(self):
        n = resolve_topic_name("/shasou", "CAM_FRONT", GT_DEPTH_IMAGE)
        assert n == "/shasou/gt/depth_cam_front/image"

    def test_pedal_names_fixed(self):
        assert PEDAL_JOINT_NAMES == ("throttle_pedal", "brake_pedal")


def _base_manifest(**overrides):
    data = dict(
        drive_id="2026-07-16_1030_vehicle01_osaka-umeda",
        uuid="7f3a0000000000000000000000000000",
        source=DataSource.REAL,
        platform="platform_lincoln_6cam-lidar",
        vehicle="vehicle01",
        ego_pose_backend=EgoPoseBackend.PPK_INS,
        calib_id="calib_v003_2026-07-01",
        date_captured="2026-07-16",
        location="osaka-umeda",
        recorder_version="v1.2.0",
        sensor_config={"LIDAR_TOP": "/sensing/lidar_top/points",
                       "CAM_FRONT": "/sensing/cam_front/image_raw/compressed"},
    )
    data.update(overrides)
    return data


class TestManifest:
    def test_valid_real_manifest(self):
        m = DriveManifest(**_base_manifest())
        assert m.status == DriveStatus.RECORDED
        assert m.archive_status == ArchiveStatus.NONE

    def test_malformed_channel_rejected(self):
        # プレフィックス無し・小文字は命名規約違反
        with pytest.raises(ValidationError):
            DriveManifest(**_base_manifest(sensor_config={"FOO_BAR": "/x"}))
        with pytest.raises(ValidationError):
            DriveManifest(**_base_manifest(sensor_config={"cam_front": "/x"}))

    def test_non_nuscenes_channel_accepted(self):
        # 7 台目や独自 RADAR 名など、命名規約を満たせば manifest 段階では通る
        # (platform sensor_rig との一致は validation.py の責務)
        m = DriveManifest(**_base_manifest(sensor_config={
            "CAM_FRONT_EXTRA": "/sensing/cam_front_extra/image_raw/compressed",
            "RADAR_REAR_LEFT": "/sensing/radar_rear_left/points",
        }))
        assert "CAM_FRONT_EXTRA" in m.sensor_config

    def test_carla_requires_gt_backend(self):
        with pytest.raises(ValidationError):
            DriveManifest(**_base_manifest(
                source=DataSource.CARLA, ego_pose_backend=EgoPoseBackend.PPK_INS))

    def test_carla_gt_backend_ok(self):
        m = DriveManifest(**_base_manifest(
            source=DataSource.CARLA, ego_pose_backend=EgoPoseBackend.CARLA_GT))
        assert m.source == DataSource.CARLA

    def test_real_rejects_carla_gt(self):
        with pytest.raises(ValidationError):
            DriveManifest(**_base_manifest(
                ego_pose_backend=EgoPoseBackend.CARLA_GT))

    def test_schema_compat(self):
        m = DriveManifest(**_base_manifest(schema_version="0.9.9"))
        assert m.is_schema_compatible("0.1.0")  # 同 MAJOR 0
        assert not m.is_schema_compatible("1.0.0")

    def test_yaml_roundtrip(self):
        m = DriveManifest(**_base_manifest())
        restored = DriveManifest.model_validate(m.model_dump())
        assert restored == m
