"""trajectory 成果物の Parquet 読み書き (optional extra [io])。

このモジュールだけ pyarrow に依存する。core 本体の規律 (pydantic のみ) を
守るため、I/O は extras に隔離してある。pyarrow 未インストール時は明示的な
エラーを出す。
"""

from __future__ import annotations

from pathlib import Path
from typing import Iterable

from ..schemas.common import Pose, QuaternionXYZW, Vector3
from ..schemas.trajectory import (
    TRAJECTORY_COLUMNS,
    PoseQuality,
    TrajectoryMetadata,
    TrajectoryPoint,
)

try:
    import pyarrow as pa
    import pyarrow.parquet as pq
    _HAS_PYARROW = True
except ImportError:  # pragma: no cover
    _HAS_PYARROW = False


_META_KEY = b"shasou_trajectory_metadata"


def _require_pyarrow() -> None:
    if not _HAS_PYARROW:
        raise ImportError(
            "trajectory_io requires pyarrow. Install with: pip install 'shasou-core[io]'"
        )


def write_trajectory(
    path: str | Path,
    metadata: TrajectoryMetadata,
    points: Iterable[TrajectoryPoint],
) -> None:
    """メタデータを Parquet の file-level metadata に、点列を行として書き出す。"""
    _require_pyarrow()
    pts = list(points)

    cols: dict[str, list] = {c: [] for c in TRAJECTORY_COLUMNS}
    for p in pts:
        cols["timestamp"].append(p.timestamp)
        cols["x"].append(p.pose.translation.x)
        cols["y"].append(p.pose.translation.y)
        cols["z"].append(p.pose.translation.z)
        cols["qx"].append(p.pose.rotation.x)
        cols["qy"].append(p.pose.rotation.y)
        cols["qz"].append(p.pose.rotation.z)
        cols["qw"].append(p.pose.rotation.w)
        cols["quality"].append(p.quality.value)
        cols["raw_quality"].append(p.raw_quality)

    table = pa.table(cols)
    # メタデータを JSON で埋め込む (成果物が自己完結する)
    table = table.replace_schema_metadata(
        {_META_KEY: metadata.model_dump_json().encode("utf-8")}
    )
    pq.write_table(table, str(path))


def read_trajectory(
    path: str | Path,
) -> tuple[TrajectoryMetadata, list[TrajectoryPoint]]:
    """write_trajectory で書いた成果物を読み戻す。"""
    _require_pyarrow()
    table = pq.read_table(str(path))

    raw_meta = (table.schema.metadata or {}).get(_META_KEY)
    if raw_meta is None:
        raise ValueError(f"{path}: shasou trajectory metadata が見つからない")
    metadata = TrajectoryMetadata.model_validate_json(raw_meta.decode("utf-8"))

    d = table.to_pydict()
    points: list[TrajectoryPoint] = []
    for i in range(table.num_rows):
        points.append(
            TrajectoryPoint(
                timestamp=d["timestamp"][i],
                pose=Pose(
                    translation=Vector3(x=d["x"][i], y=d["y"][i], z=d["z"][i]),
                    rotation=QuaternionXYZW(
                        x=d["qx"][i], y=d["qy"][i], z=d["qz"][i], w=d["qw"][i]
                    ),
                ),
                quality=PoseQuality(d["quality"][i]),
                raw_quality=d["raw_quality"][i],
            )
        )
    return metadata, points
