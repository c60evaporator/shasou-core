"""shasou-core: shasou エコシステムの共有スキーマと規約。

規律: このパッケージのランタイム依存は pydantic のみ。
フレームワーク (FastAPI, SQLAlchemy, ROS) への依存は禁止。
"""

from .version import SCHEMA_VERSION, major
from .schemas.common import (
    DataSource,
    FrozenModel,
    Modality,
    Pose,
    QuaternionXYZW,
    ShasouModel,
    TimestampNs,
    Token,
    Vector3,
    derived_token,
    new_token,
    ns_to_seconds,
    ns_to_us,
    seconds_to_ns,
)

__all__ = [
    "SCHEMA_VERSION",
    "major",
    "DataSource",
    "FrozenModel",
    "Modality",
    "Pose",
    "QuaternionXYZW",
    "ShasouModel",
    "TimestampNs",
    "Token",
    "Vector3",
    "derived_token",
    "new_token",
    "ns_to_seconds",
    "ns_to_us",
    "seconds_to_ns",
    "DriveManifest",
    "DriveStatus",
    "ArchiveStatus",
    "EgoPoseBackend",
    "TrajectoryMetadata",
    "TrajectoryPoint",
    "Datum",
    "PoseQuality",
    "TRAJECTORY_COLUMNS",
    "EventTag",
    "EventType",
    "EventSource",
    "TopicStat",
    "TopicStats",
    "DiskStats",
    "CanSpec",
    "SpeedSignRule",
    "BrakeNormalization",
    "VehicleDimensions",
    "VehicleType",
    "Vehicle",
]

from .schemas.common import EgoPoseBackend  # noqa: E402
from .schemas.manifest import (  # noqa: E402
    ArchiveStatus,
    DriveManifest,
    DriveStatus,
)
from .schemas.events import (  # noqa: E402
    EventSource,
    EventTag,
    EventType,
)
from .schemas.health import (  # noqa: E402
    DiskStats,
    TopicStat,
    TopicStats,
)
from .schemas.trajectory import (  # noqa: E402
    TRAJECTORY_COLUMNS,
    Datum,
    PoseQuality,
    TrajectoryMetadata,
    TrajectoryPoint,
)
from .schemas.vehicle import (  # noqa: E402
    BrakeNormalization,
    CanSpec,
    SpeedSignRule,
    Vehicle,
    VehicleDimensions,
    VehicleType,
)
