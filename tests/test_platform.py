import math

import pytest
from pydantic import ValidationError

from shasou_core.schemas.common import Modality, Pose, QuaternionXYZW, Vector3
from shasou_core.schemas.platform import (
    BrakeNormalization,
    CameraConfig,
    CameraIntrinsicsModel,
    ChannelSpec,
    Platform,
    SpeedSignRule,
    VehicleParams,
)


def _full_vehicle_params(**overrides):
    data = dict(
        vehicle_type="lincoln_mkz",
        steering_gear_ratio=15.7,
        max_steer_angle_rad=0.61,
        speed_sign_rule=SpeedSignRule.ABS_WITH_REVERSE_FLAG,
        brake_normalization=BrakeNormalization.STROKE,
        base_link_offset=Vector3(x=-1.37, y=0.0, z=-0.32),
    )
    data.update(overrides)
    return data


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


class TestVehicleParams:
    def test_minimal(self):
        # 手書き platform 定義を想定し、vehicle_type 以外はすべて optional
        p = VehicleParams(vehicle_type="lincoln_mkz")
        assert p.steering_gear_ratio is None
        assert p.base_link_offset is None

    def test_full(self):
        p = VehicleParams(**_full_vehicle_params())
        assert p.max_steer_angle_rad == pytest.approx(0.61)
        assert p.base_link_offset.x == pytest.approx(-1.37)

    def test_nonpositive_ratio_rejected(self):
        with pytest.raises(ValidationError):
            VehicleParams(**_full_vehicle_params(steering_gear_ratio=0.0))
        with pytest.raises(ValidationError):
            VehicleParams(**_full_vehicle_params(steering_gear_ratio=-15.7))

    def test_steer_angle_bounds(self):
        with pytest.raises(ValidationError):
            VehicleParams(**_full_vehicle_params(max_steer_angle_rad=0.0))
        with pytest.raises(ValidationError):
            VehicleParams(**_full_vehicle_params(max_steer_angle_rad=math.pi + 0.1))

    def test_enums_from_string(self):
        # JSON/YAML からは文字列値で入る
        p = VehicleParams(
            vehicle_type="lincoln_mkz",
            speed_sign_rule="signed",
            brake_normalization="pressure",
        )
        assert p.speed_sign_rule == SpeedSignRule.SIGNED
        assert p.brake_normalization == BrakeNormalization.PRESSURE

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            VehicleParams(vehicle_type="lincoln_mkz", wheelbase_m=2.85)


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


def _platform(**overrides):
    data = dict(
        platform_id="platform_lincoln_6cam-lidar",
        vehicle_type="lincoln_mkz",
        sensor_rig=[
            ChannelSpec(**_camera_spec()),
            ChannelSpec(channel="LIDAR_TOP", modality=Modality.LIDAR),
        ],
        vehicle_params=VehicleParams(**_full_vehicle_params()),
    )
    data.update(overrides)
    return data


class TestPlatform:
    def test_valid(self):
        p = Platform(**_platform())
        assert p.channel_names() == {"CAM_FRONT", "LIDAR_TOP"}
        assert p.channels_by_modality(Modality.CAMERA) == ["CAM_FRONT"]

    def test_vehicle_params_optional(self):
        p = Platform(**_platform(vehicle_params=None))
        assert p.vehicle_params is None

    def test_modality_mismatch_rejected(self):
        # 既存 _modality_matches_name の回帰: 名前と modality の矛盾を弾く
        with pytest.raises(ValidationError):
            Platform(**_platform(sensor_rig=[
                ChannelSpec.model_construct(
                    channel="CAM_FRONT", modality=Modality.LIDAR,
                    nominal_mount=None, camera=None,
                ),
            ]))

    def test_vehicle_type_mismatch_rejected(self):
        with pytest.raises(ValidationError):
            Platform(**_platform(
                vehicle_params=VehicleParams(
                    **_full_vehicle_params(vehicle_type="prius")
                ),
            ))

    def test_json_roundtrip(self):
        p = Platform(**_platform())
        restored = Platform.model_validate_json(p.model_dump_json())
        assert restored == p

    def test_yaml_roundtrip(self):
        # YAML 経由と等価な dict 形式での往復 (test_topics_manifest.py と同パターン)
        p = Platform(**_platform())
        restored = Platform.model_validate(p.model_dump())
        assert restored == p
