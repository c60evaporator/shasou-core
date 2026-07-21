"""shasou 全体で共有する定数と単位規約。

ここに書かれた規約は shasou エコシステムの「憲法」であり、
recorder / studio / エクスポータのすべてが従う。変更は SCHEMA_VERSION の
インクリメントを伴う。

単位規約 (unit conventions)
---------------------------
- 時刻:      エポックからのナノ秒整数 (ROS 2 ネイティブ)。
             CARLA ソースではシミュレーション時刻の ns。
             nuScenes のマイクロ秒への変換はエクスポータの責務。
- 角度:      ラジアン。舵角は前輪実舵角で左転舵が正 (REP-103 の +Z 回転と整合)。
- 距離:      メートル。
- 速度:      m/s。車体前方 +X が正、後退は負。
- 座標系:    右手系のみ。左手系 (CARLA / Unreal) はブリッジ境界で変換済みで
             あることを前提とし、shasou の世界に左手系のデータは存在しない。
"""

import re
from typing import Final, Optional

# --------------------------------------------------------------------------
# チャネル名の規約
# --------------------------------------------------------------------------
# 実際のチャネル集合の「正」は platform 定義 (sensor_rig) である。
# core はチャネル名の *命名規約* を規定するのみで、特定の台数構成を強制しない。
#
# 規約:
#   - modality プレフィックス (CAM_ / LIDAR_ / RADAR_) で始まる
#   - 続くのは大文字英字・数字・アンダースコア
# これにより CAM_FRONT / CAM_FRONT_LEFT / CAM_FRONT_EXTRA / LIDAR_TOP /
# RADAR_FRONT_LEFT などは通り、FOO_BAR / cam_front (小文字) は弾かれる。

CAM_PREFIX: Final = "CAM_"
LIDAR_PREFIX: Final = "LIDAR_"
RADAR_PREFIX: Final = "RADAR_"

MODALITY_PREFIXES: Final[tuple[str, ...]] = (CAM_PREFIX, LIDAR_PREFIX, RADAR_PREFIX)

# プレフィックスの後ろに続く本体部分 (大文字英数字とアンダースコア、1 文字以上)
_CHANNEL_BODY = r"[A-Z0-9]+(?:_[A-Z0-9]+)*"
CHANNEL_NAME_PATTERN: Final = re.compile(
    rf"^(?:{CAM_PREFIX}|{LIDAR_PREFIX}|{RADAR_PREFIX}){_CHANNEL_BODY}$"
)


def is_valid_channel_name(name: str) -> bool:
    """チャネル名が命名規約を満たすか (modality プレフィックス + 文字種)。

    実在するチャネルかどうか (platform に定義されているか) は判定しない。
    それは validation.py の platform 照合の責務。
    """
    return bool(CHANNEL_NAME_PATTERN.match(name))


def channel_modality(name: str) -> Optional[str]:
    """チャネル名から modality を推定して返す ('camera'/'lidar'/'radar')。

    規約を満たさない名前には None を返す。
    """
    if not is_valid_channel_name(name):
        return None
    if name.startswith(CAM_PREFIX):
        return "camera"
    if name.startswith(LIDAR_PREFIX):
        return "lidar"
    if name.startswith(RADAR_PREFIX):
        return "radar"
    return None


# --------------------------------------------------------------------------
# nuScenes 標準チャネル (参考・デフォルト)
# --------------------------------------------------------------------------
# これらは nuScenes 準拠の代表的な構成であり、CARLA の当面のデフォルトや
# platform 定義を書く際の雛形として使う。*上限でも唯一の正でもない* —
# 実際の構成は platform ごとに自由に定義できる。

CAM_FRONT: Final = "CAM_FRONT"
CAM_FRONT_LEFT: Final = "CAM_FRONT_LEFT"
CAM_FRONT_RIGHT: Final = "CAM_FRONT_RIGHT"
CAM_BACK: Final = "CAM_BACK"
CAM_BACK_LEFT: Final = "CAM_BACK_LEFT"
CAM_BACK_RIGHT: Final = "CAM_BACK_RIGHT"

NUSCENES_CAMERA_CHANNELS: Final[tuple[str, ...]] = (
    CAM_FRONT,
    CAM_FRONT_LEFT,
    CAM_FRONT_RIGHT,
    CAM_BACK,
    CAM_BACK_LEFT,
    CAM_BACK_RIGHT,
)

LIDAR_TOP: Final = "LIDAR_TOP"
NUSCENES_LIDAR_CHANNELS: Final[tuple[str, ...]] = (LIDAR_TOP,)

# nuScenes 準拠の RADAR 標準名 (参考)
RADAR_FRONT: Final = "RADAR_FRONT"
NUSCENES_RADAR_CHANNELS: Final[tuple[str, ...]] = (RADAR_FRONT,)

NUSCENES_SENSOR_CHANNELS: Final[tuple[str, ...]] = (
    NUSCENES_CAMERA_CHANNELS + NUSCENES_LIDAR_CHANNELS + NUSCENES_RADAR_CHANNELS
)

# --------------------------------------------------------------------------
# トピック名前空間
# --------------------------------------------------------------------------
TOPIC_NAMESPACE: Final = "/shasou"

# --------------------------------------------------------------------------
# 時刻の単位換算
# --------------------------------------------------------------------------
NS_PER_SEC: Final = 1_000_000_000
NS_PER_MS: Final = 1_000_000
NS_PER_US: Final = 1_000

# --------------------------------------------------------------------------
# キーフレーム規約
# --------------------------------------------------------------------------
# sample (キーフレーム) の既定レート。LiDAR 周期の整数倍であることを
# 変換パイプラインが検証する (nuScenes 準拠の 2Hz)。
DEFAULT_KEYFRAME_HZ: Final = 2.0
