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
]
