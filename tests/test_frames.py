import pytest

from shasou_core.constants import (
    CAM_FRONT,
    LIDAR_TOP,
    NUSCENES_CAMERA_CHANNELS,
    NUSCENES_LIDAR_CHANNELS,
)
from shasou_core.frames import (
    FRAME_BASE_LINK,
    expected_static_transforms,
    optical_frame,
    sensor_frame,
)


from shasou_core.constants import channel_modality, is_valid_channel_name


def test_channel_naming_convention():
    assert is_valid_channel_name("CAM_FRONT")
    assert is_valid_channel_name("CAM_FRONT_EXTRA")
    assert is_valid_channel_name("LIDAR_TOP")
    assert is_valid_channel_name("RADAR_FRONT_LEFT")
    # 違反
    assert not is_valid_channel_name("cam_front")   # 小文字
    assert not is_valid_channel_name("FOO_BAR")     # 未知プレフィックス
    assert not is_valid_channel_name("CAM_")        # 本体なし
    assert not is_valid_channel_name("CAM_FRONT!")  # 記号


def test_channel_modality_inference():
    assert channel_modality("CAM_FRONT_EXTRA") == "camera"
    assert channel_modality("LIDAR_TOP") == "lidar"
    assert channel_modality("RADAR_FRONT") == "radar"
    assert channel_modality("FOO_BAR") is None


def test_sensor_frame_naming():
    assert sensor_frame(CAM_FRONT) == "cam_front"
    assert sensor_frame(LIDAR_TOP) == "lidar_top"


def test_optical_frame_for_camera():
    assert optical_frame(CAM_FRONT) == "cam_front_optical"


def test_optical_frame_rejects_non_camera():
    with pytest.raises(ValueError):
        optical_frame(LIDAR_TOP)


def test_expected_static_transforms_nuscenes_rig():
    pairs = expected_static_transforms(
        camera_channels=NUSCENES_CAMERA_CHANNELS,
        lidar_channels=NUSCENES_LIDAR_CHANNELS,
    )
    # imu + gnss + lidar_top + 6 カメラ x (取り付け + 光学) = 2 + 1 + 12
    assert len(pairs) == 2 + len(NUSCENES_LIDAR_CHANNELS) + 2 * len(NUSCENES_CAMERA_CHANNELS)
    assert (FRAME_BASE_LINK, "lidar_top") in pairs
    assert ("cam_back_left", "cam_back_left_optical") in pairs
    # 動的 tf (map -> base_link) は含まれないこと
    assert all(parent != "map" for parent, _ in pairs)


def test_expected_static_transforms_custom_rig():
    # 7 カメラ + RADAR を含む非 nuScenes 構成でも扱える
    pairs = expected_static_transforms(
        camera_channels=("CAM_FRONT", "CAM_FRONT_EXTRA"),
        lidar_channels=("LIDAR_TOP",),
        radar_channels=("RADAR_FRONT",),
    )
    assert ("cam_front_extra", "cam_front_extra_optical") in pairs
    assert (FRAME_BASE_LINK, "radar_front") in pairs
