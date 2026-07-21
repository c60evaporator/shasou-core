import pytest

from shasou_core.constants import CAM_FRONT, CAMERA_CHANNELS, LIDAR_TOP
from shasou_core.frames import (
    FRAME_BASE_LINK,
    expected_static_transforms,
    optical_frame,
    sensor_frame,
)


def test_sensor_frame_naming():
    assert sensor_frame(CAM_FRONT) == "cam_front"
    assert sensor_frame(LIDAR_TOP) == "lidar_top"


def test_optical_frame_for_camera():
    assert optical_frame(CAM_FRONT) == "cam_front_optical"


def test_optical_frame_rejects_non_camera():
    with pytest.raises(ValueError):
        optical_frame(LIDAR_TOP)


def test_expected_static_transforms_default():
    pairs = expected_static_transforms()
    # imu + gnss + lidar_top + 6 カメラ x (取り付け + 光学) = 3 + 12
    assert len(pairs) == 3 + 2 * len(CAMERA_CHANNELS)
    assert (FRAME_BASE_LINK, "lidar_top") in pairs
    assert ("cam_back_left", "cam_back_left_optical") in pairs
    # 動的 tf (map -> base_link) は含まれないこと
    assert all(parent != "map" for parent, _ in pairs)
