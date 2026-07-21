"""座標フレーム規約 (tf tree の定義)。

フレームツリー
--------------
    map                       右手 ENU (X東, Y北, Z上)。原点の測地座標 (datum) は
     |                        trajectory 成果物のメタデータに記録される。
     └─ base_link             車体フレーム。X前方, Y左, Z上 (REP-103)。
         |                    原点 = 後軸中心を地面高さへ投影した点 (nuScenes の
         |                    ego フレームと同一定義)。車両モデル原点からの
         |                    オフセットは CalibrationSet に記録する。
         ├─ lidar_top
         ├─ imu_link
         ├─ gnss_link
         └─ cam_front ─ cam_front_optical      (x6 カメラ)

- センサフレーム: チャネル名の小文字 (CAM_FRONT -> cam_front)。車体規約
  (X前方) で取り付け姿勢を表す。
- 光学フレーム: カメラのみ、`_optical` サフィックス。Z前方, X右, Y下
  (REP-103 光学規約)。cam_* -> cam_*_optical は固定回転。
  画像トピックの header.frame_id は光学フレームを指す。
  nuScenes の calibrated_sensor (カメラ) も同じ光学規約なので、
  エクスポータは光学フレームの値を素通しできる。
- 動的 tf (map -> base_link) は bag に記録しない。ego pose はトピック
  (gt/ego_odom) と trajectory 成果物で表現する。/tf_static のみ記録する。
"""

from .constants import CAMERA_CHANNELS, LIDAR_CHANNELS

FRAME_MAP = "map"
FRAME_BASE_LINK = "base_link"
FRAME_IMU = "imu_link"
FRAME_GNSS = "gnss_link"

OPTICAL_SUFFIX = "_optical"


def sensor_frame(channel: str) -> str:
    """チャネル名からセンサフレーム名を返す (CAM_FRONT -> cam_front)。"""
    return channel.lower()


def optical_frame(channel: str) -> str:
    """カメラチャネルの光学フレーム名を返す (CAM_FRONT -> cam_front_optical)。

    カメラ以外のチャネルに対しては ValueError。
    """
    if channel not in CAMERA_CHANNELS:
        raise ValueError(f"optical frame is defined only for cameras, got {channel!r}")
    return sensor_frame(channel) + OPTICAL_SUFFIX


def expected_static_transforms(
    camera_channels: tuple[str, ...] = CAMERA_CHANNELS,
    lidar_channels: tuple[str, ...] = LIDAR_CHANNELS,
) -> list[tuple[str, str]]:
    """/tf_static に存在すべき (parent, child) ペアの一覧を返す。

    recorder の起動時検証と studio の取り込み時検証が同じ定義を参照する。
    """
    pairs: list[tuple[str, str]] = [
        (FRAME_BASE_LINK, FRAME_IMU),
        (FRAME_BASE_LINK, FRAME_GNSS),
    ]
    for ch in lidar_channels:
        pairs.append((FRAME_BASE_LINK, sensor_frame(ch)))
    for ch in camera_channels:
        pairs.append((FRAME_BASE_LINK, sensor_frame(ch)))
        pairs.append((sensor_frame(ch), optical_frame(ch)))
    return pairs
