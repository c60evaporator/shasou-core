import math

import pytest
from pydantic import ValidationError

from shasou_core.schemas.calibration import (
    CalibrationSet,
    CameraIntrinsics,
    SensorCalibEntry,
    SensorExtrinsics,
)
from shasou_core.schemas.common import QuaternionXYZW, Vector3, derived_token
from shasou_core.schemas.platform import CameraIntrinsicsModel


def _extrinsics(**overrides):
    data = dict(
        translation=Vector3(x=1.5, y=0.0, z=1.6),
        rotation=QuaternionXYZW.identity(),
    )
    data.update(overrides)
    return SensorExtrinsics(**data)


def _intrinsics(**overrides):
    data = dict(
        model=CameraIntrinsicsModel.PINHOLE_PLUMB_BOB,
        fx=1266.4,
        fy=1266.4,
        cx=816.3,
        cy=491.5,
        width=1600,
        height=900,
        distortion=[-0.35, 0.14, 0.0002, -0.0001, -0.03],
    )
    data.update(overrides)
    return data


def _camera_entry():
    return SensorCalibEntry(
        channel="CAM_FRONT",
        extrinsics=_extrinsics(),
        intrinsics=CameraIntrinsics(**_intrinsics()),
    )


def _lidar_entry():
    return SensorCalibEntry(
        channel="LIDAR_TOP",
        extrinsics=_extrinsics(translation=Vector3(x=0.9, y=0.0, z=1.8)),
    )


def _calibration_set(**overrides):
    data = dict(
        calib_id="calib_v003_2026-07-01",
        captured_at="2026-07-01",
        entries=[_camera_entry(), _lidar_entry()],
    )
    data.update(overrides)
    return CalibrationSet(**data)


class TestCameraIntrinsics:
    def test_valid(self):
        i = CameraIntrinsics(**_intrinsics())
        assert i.model == CameraIntrinsicsModel.PINHOLE_PLUMB_BOB
        assert len(i.distortion) == 5

    def test_empty_distortion_allowed(self):
        # CARLA の理想ピンホール等、無歪みは空リストで表現できる
        i = CameraIntrinsics(**_intrinsics(distortion=[]))
        assert i.distortion == []

    def test_wrong_distortion_length_rejected(self):
        with pytest.raises(ValidationError):
            CameraIntrinsics(**_intrinsics(distortion=[-0.35, 0.14, 0.0002]))
        # fisheye は 4 個。plumb_bob の 5 個は弾く
        with pytest.raises(ValidationError):
            CameraIntrinsics(**_intrinsics(
                model=CameraIntrinsicsModel.FISHEYE_EQUIDISTANT,
                distortion=[-0.35, 0.14, 0.0002, -0.0001, -0.03],
            ))

    def test_nonpositive_focal_rejected(self):
        with pytest.raises(ValidationError):
            CameraIntrinsics(**_intrinsics(fx=0.0))
        with pytest.raises(ValidationError):
            CameraIntrinsics(**_intrinsics(fy=-1266.4))

    def test_as_matrix(self):
        i = CameraIntrinsics(**_intrinsics())
        assert i.as_matrix() == [
            [1266.4, 0.0, 816.3],
            [0.0, 1266.4, 491.5],
            [0.0, 0.0, 1.0],
        ]

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            CameraIntrinsics(**_intrinsics(skew=0.0))


class TestSensorCalibEntry:
    def test_camera_entry_valid(self):
        e = _camera_entry()
        assert e.intrinsics is not None

    def test_lidar_entry_without_intrinsics_valid(self):
        # カメラ以外は intrinsics=None を許容 (というより必須で None)
        e = _lidar_entry()
        assert e.intrinsics is None

    def test_intrinsics_on_lidar_rejected(self):
        with pytest.raises(ValidationError):
            SensorCalibEntry(
                channel="LIDAR_TOP",
                extrinsics=_extrinsics(),
                intrinsics=CameraIntrinsics(**_intrinsics()),
            )

    def test_camera_without_intrinsics_rejected(self):
        with pytest.raises(ValidationError):
            SensorCalibEntry(channel="CAM_FRONT", extrinsics=_extrinsics())

    def test_invalid_channel_name_rejected(self):
        # 既存 _valid_name の回帰: 小文字・プレフィックス無しは弾く
        with pytest.raises(ValidationError):
            SensorCalibEntry(channel="cam_front", extrinsics=_extrinsics(),
                             intrinsics=CameraIntrinsics(**_intrinsics()))
        with pytest.raises(ValidationError):
            SensorCalibEntry(channel="FOO_BAR", extrinsics=_extrinsics())

    def test_unnormalized_quaternion_rejected(self):
        # common.QuaternionXYZW の正規化検証が extrinsics 経由でも効くこと
        with pytest.raises(ValidationError):
            SensorCalibEntry(
                channel="LIDAR_TOP",
                extrinsics=SensorExtrinsics(
                    translation=Vector3(x=0.0, y=0.0, z=0.0),
                    rotation=dict(x=0.5, y=0.5, z=0.5, w=0.9),
                ),
            )

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            SensorCalibEntry(
                channel="LIDAR_TOP", extrinsics=_extrinsics(), rms_error=0.12
            )


class TestCalibrationSet:
    def test_token_deterministic(self):
        c = _calibration_set()
        t1 = c.calibrated_sensor_token("CAM_FRONT")
        t2 = c.calibrated_sensor_token("CAM_FRONT")
        assert t1 == t2
        assert t1 == derived_token(c.calib_id, "CAM_FRONT")
        assert t1 != c.calibrated_sensor_token("LIDAR_TOP")

    def test_tokens_one_per_entry(self):
        # 1 CalibrationSet → N calibrated_sensor (1:N 展開)
        c = _calibration_set()
        tokens = c.calibrated_sensor_tokens()
        assert set(tokens) == {"CAM_FRONT", "LIDAR_TOP"}
        assert len(set(tokens.values())) == 2
        assert tokens["CAM_FRONT"] == c.calibrated_sensor_token("CAM_FRONT")

    def test_unknown_channel_raises(self):
        with pytest.raises(KeyError):
            _calibration_set().calibrated_sensor_token("CAM_BACK")

    def test_json_roundtrip(self):
        c = _calibration_set()
        restored = CalibrationSet.model_validate_json(c.model_dump_json())
        assert restored == c

    def test_yaml_roundtrip(self):
        # YAML 経由と等価な dict 形式での往復 (既存テストと同パターン)
        c = _calibration_set()
        restored = CalibrationSet.model_validate(c.model_dump())
        assert restored == c
