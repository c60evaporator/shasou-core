import pytest

from shasou_core.schemas.common import (
    EgoPoseBackend,
    Pose,
    QuaternionXYZW,
    Vector3,
)
from shasou_core.schemas.trajectory import (
    TRAJECTORY_COLUMNS,
    Datum,
    PoseQuality,
    TrajectoryMetadata,
    TrajectoryPoint,
)


def _datum():
    return Datum(latitude=34.7, longitude=135.5, altitude=10.0)


def _meta(**overrides):
    data = dict(
        drive_id="2026-07-16_1030_vehicle01_osaka-umeda",
        backend=EgoPoseBackend.PPK_INS,
        backend_version="v1.0.0",
        datum=_datum(),
        point_count=2,
        start_timestamp=1000,
        end_timestamp=2000,
    )
    data.update(overrides)
    return TrajectoryMetadata(**data)


class TestTrajectoryMetadata:
    def test_valid(self):
        m = _meta()
        assert m.frame_id == "map"

    def test_time_order_enforced(self):
        with pytest.raises(ValueError):
            _meta(start_timestamp=2000, end_timestamp=1000)

    def test_artifact_key_distinguishes_backends(self):
        # 選択肢 B: 同一 drive で backend 違いの成果物が衝突しない
        a = _meta(backend=EgoPoseBackend.PPK_INS).artifact_key()
        b = _meta(backend=EgoPoseBackend.LIO_GRAPH).artifact_key()
        assert a != b

    def test_artifact_key_distinguishes_versions(self):
        a = _meta(backend_version="v1.0.0").artifact_key()
        b = _meta(backend_version="v2.0.0").artifact_key()
        assert a != b

    def test_datum_bounds(self):
        with pytest.raises(ValueError):
            Datum(latitude=200.0, longitude=0.0, altitude=0.0)


class TestTrajectoryColumns:
    def test_columns_stable(self):
        # 列仕様は成果物の契約。変更は SCHEMA_VERSION を伴う
        assert TRAJECTORY_COLUMNS == (
            "timestamp", "x", "y", "z", "qx", "qy", "qz", "qw",
            "quality", "raw_quality",
        )


class TestParquetRoundtrip:
    def test_write_read(self, tmp_path):
        pytest.importorskip("pyarrow")
        from shasou_core.io.trajectory_io import read_trajectory, write_trajectory

        meta = _meta()
        points = [
            TrajectoryPoint(
                timestamp=1000,
                pose=Pose(
                    translation=Vector3(x=0.0, y=0.0, z=0.0),
                    rotation=QuaternionXYZW.identity(),
                ),
                quality=PoseQuality.HIGH,
                raw_quality=4.0,
            ),
            TrajectoryPoint(
                timestamp=2000,
                pose=Pose(
                    translation=Vector3(x=1.0, y=-0.5, z=0.1),
                    rotation=QuaternionXYZW.identity(),
                ),
                quality=PoseQuality.MEDIUM,
                raw_quality=None,
            ),
        ]
        path = tmp_path / "traj.parquet"
        write_trajectory(path, meta, points)

        rmeta, rpoints = read_trajectory(path)
        assert rmeta == meta
        assert rpoints == points
        assert rpoints[1].raw_quality is None
