import math

import pytest
from pydantic import ValidationError

from shasou_core.schemas.common import Modality, Pose, QuaternionXYZW, Vector3
from shasou_core.schemas.platform import (
    CameraConfig,
    CameraIntrinsicsModel,
    ChannelSpec,
    Platform,
)


def _camera_spec(**overrides):
    data = dict(
        channel="CAM_FRONT",
        modality=Modality.CAMERA,
        nominal_mount=Pose(
            translation=Vector3(x=1.5, y=0.0, z=1.6),
            rotation=QuaternionXYZW.identity(),
        ),
        camera=CameraConfig(
            width_px=1600,
            height_px=900,
            horizontal_fov_rad=math.radians(70),
            intrinsics_model=CameraIntrinsicsModel.PINHOLE_PLUMB_BOB,
        ),
    )
    data.update(overrides)
    return data


class TestChannelSpec:
    def test_camera_with_config(self):
        spec = ChannelSpec(**_camera_spec())
        assert spec.camera.width_px == 1600
        assert spec.camera.intrinsics_model == CameraIntrinsicsModel.PINHOLE_PLUMB_BOB

    def test_minimal_non_camera(self):
        spec = ChannelSpec(channel="LIDAR_TOP", modality=Modality.LIDAR)
        assert spec.nominal_mount is None
        assert spec.camera is None

    def test_camera_config_on_lidar_rejected(self):
        with pytest.raises(ValidationError):
            ChannelSpec(
                channel="LIDAR_TOP",
                modality=Modality.LIDAR,
                camera=CameraConfig(intrinsics_model="pinhole_plumb_bob"),
            )

    def test_invalid_channel_name_rejected(self):
        with pytest.raises(ValidationError):
            ChannelSpec(channel="cam_front", modality=Modality.CAMERA)

    def test_resolution_requires_both(self):
        with pytest.raises(ValidationError):
            CameraConfig(width_px=1600)
        with pytest.raises(ValidationError):
            CameraConfig(height_px=900)

    def test_fov_bounds(self):
        with pytest.raises(ValidationError):
            CameraConfig(horizontal_fov_rad=0.0)
        with pytest.raises(ValidationError):
            CameraConfig(horizontal_fov_rad=math.tau + 0.1)

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            ChannelSpec(
                channel="CAM_FRONT", modality=Modality.CAMERA, fps=20
            )


class TestExpectedHz:
    """期待レートは platform 定義が持つ (recorder の drop_rate 算出の源)。"""

    def test_default_is_none(self):
        # platform 定義は手書きされうるので optional。無ければ recorder は
        # drop_rate を None にする
        assert ChannelSpec(**_camera_spec()).expected_hz is None
        assert ChannelSpec(
            channel="LIDAR_TOP", modality=Modality.LIDAR).expected_hz is None

    def test_positive_value_accepted(self):
        spec = ChannelSpec(**_camera_spec(expected_hz=20.0))
        assert spec.expected_hz == 20.0

    @pytest.mark.parametrize("hz", [0, 0.0, -1.0])
    def test_non_positive_rejected(self, hz):
        with pytest.raises(ValidationError):
            ChannelSpec(**_camera_spec(expected_hz=hz))

    def test_any_modality_can_declare_rate(self):
        # modality に依らない共通概念なので CameraConfig ではなく ChannelSpec 直下
        lidar = ChannelSpec(
            channel="LIDAR_TOP", modality=Modality.LIDAR, expected_hz=10.0)
        radar = ChannelSpec(
            channel="RADAR_FRONT", modality=Modality.RADAR, expected_hz=13.0)
        assert (lidar.expected_hz, radar.expected_hz) == (10.0, 13.0)

    def test_json_roundtrip(self):
        spec = ChannelSpec(**_camera_spec(expected_hz=20.0))
        assert ChannelSpec.model_validate_json(spec.model_dump_json()) == spec

    def test_platform_json_roundtrip(self):
        p = Platform(**_platform(sensor_rig=[
            ChannelSpec(**_camera_spec(expected_hz=20.0)),
            ChannelSpec(
                channel="LIDAR_TOP", modality=Modality.LIDAR, expected_hz=10.0),
        ]))
        assert Platform.model_validate_json(p.model_dump_json()) == p


def _platform(**overrides):
    data = dict(
        platform_id="platform_lincoln_6cam-lidar",
        vehicle_type="lincoln_mkz",
        sensor_rig=[
            ChannelSpec(**_camera_spec()),
            ChannelSpec(channel="LIDAR_TOP", modality=Modality.LIDAR),
        ],
    )
    data.update(overrides)
    return data


class TestPlatform:
    def test_valid(self):
        p = Platform(**_platform())
        assert p.channel_names() == {"CAM_FRONT", "LIDAR_TOP"}
        assert p.channels_by_modality(Modality.CAMERA) == ["CAM_FRONT"]

    def test_vehicle_params_field_removed(self):
        # 車両パラメータは vehicle.py へ移設済み。旧フィールドは extra=forbid で弾く
        with pytest.raises(ValidationError):
            Platform(**_platform(vehicle_params={"steering_gear_ratio": 15.7}))

    def test_modality_mismatch_rejected(self):
        # 既存 _modality_matches_name の回帰: 名前と modality の矛盾を弾く
        with pytest.raises(ValidationError):
            Platform(**_platform(sensor_rig=[
                ChannelSpec.model_construct(
                    channel="CAM_FRONT", modality=Modality.LIDAR,
                    nominal_mount=None, camera=None,
                ),
            ]))

    def test_json_roundtrip(self):
        p = Platform(**_platform())
        restored = Platform.model_validate_json(p.model_dump_json())
        assert restored == p

    def test_yaml_roundtrip(self):
        # YAML 経由と等価な dict 形式での往復 (test_topics_manifest.py と同パターン)
        p = Platform(**_platform())
        restored = Platform.model_validate(p.model_dump())
        assert restored == p
