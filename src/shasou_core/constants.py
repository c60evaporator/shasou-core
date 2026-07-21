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

from typing import Final

# --------------------------------------------------------------------------
# 正規チャネル名 (nuScenes 準拠)
# --------------------------------------------------------------------------
CAM_FRONT: Final = "CAM_FRONT"
CAM_FRONT_LEFT: Final = "CAM_FRONT_LEFT"
CAM_FRONT_RIGHT: Final = "CAM_FRONT_RIGHT"
CAM_BACK: Final = "CAM_BACK"
CAM_BACK_LEFT: Final = "CAM_BACK_LEFT"
CAM_BACK_RIGHT: Final = "CAM_BACK_RIGHT"

CAMERA_CHANNELS: Final[tuple[str, ...]] = (
    CAM_FRONT,
    CAM_FRONT_LEFT,
    CAM_FRONT_RIGHT,
    CAM_BACK,
    CAM_BACK_LEFT,
    CAM_BACK_RIGHT,
)

LIDAR_TOP: Final = "LIDAR_TOP"
LIDAR_CHANNELS: Final[tuple[str, ...]] = (LIDAR_TOP,)

# 将来拡張 (nuScenes 準拠名: RADAR_FRONT, RADAR_FRONT_LEFT, ...)
RADAR_CHANNELS: Final[tuple[str, ...]] = ()

ALL_SENSOR_CHANNELS: Final[tuple[str, ...]] = (
    CAMERA_CHANNELS + LIDAR_CHANNELS + RADAR_CHANNELS
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
