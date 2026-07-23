"""MCAP トピック規約をデータとして定義する。

このモジュールは「トピック名・ROS 型・必須/optional フィールド・座標フレーム」
の契約を Pydantic モデルで表現する。ROS 型そのものへの依存は recorder の責務で、
core は型名を文字列として持つだけ (フレームワーク非依存の規律)。

recorder の起動時検証と studio の取り込み時検証が、この同じ定義を参照する。

トピック名について
------------------
sensor_config (manifest) の「チャネル -> トピック名」対応が各ユーザの実際の
トピック名の正である。ここで定義するのは modality ごとの「型と必須フィールド」
と、可変部を除いた命名規約 (末尾セグメント等) のみ。

QoS と記録対象について
----------------------
契約は「型」だけでなく publisher 側の QoS (DDS の接続条件) と、bag への記録
対象かどうか (`TopicContract.recorded`) も持つ。publish はされるが録らない
トピック (/tf、gt/object_attributes) を契約として認知することで、validation が
それらを「想定外のトピック」と誤検知せずに済む。
"""

from __future__ import annotations

from enum import Enum

from pydantic import Field

from ..constants import TOPIC_NAMESPACE
from .common import DataSource, FrozenModel, Modality, ShasouModel

# --------------------------------------------------------------------------
# ROS メッセージ型 (文字列定数)
# --------------------------------------------------------------------------


class RosType(str, Enum):
    COMPRESSED_IMAGE = "sensor_msgs/msg/CompressedImage"
    IMAGE = "sensor_msgs/msg/Image"
    CAMERA_INFO = "sensor_msgs/msg/CameraInfo"
    POINT_CLOUD2 = "sensor_msgs/msg/PointCloud2"
    IMU = "sensor_msgs/msg/Imu"
    NAV_SAT_FIX = "sensor_msgs/msg/NavSatFix"
    ODOMETRY = "nav_msgs/msg/Odometry"
    PATH = "nav_msgs/msg/Path"
    TF_MESSAGE = "tf2_msgs/msg/TFMessage"
    CLOCK = "rosgraph_msgs/msg/Clock"
    BOOL = "std_msgs/msg/Bool"
    STRING = "std_msgs/msg/String"
    # ackermann_msgs は準標準 (別 apt パッケージ)
    ACKERMANN_DRIVE_STAMPED = "ackermann_msgs/msg/AckermannDriveStamped"
    JOINT_STATE = "sensor_msgs/msg/JointState"
    # shasou 独自 (shasou_msgs, recorder リポジトリで定義)
    EVENT_TAG = "shasou_msgs/msg/EventTag"


# --------------------------------------------------------------------------
# PointCloud2 フィールド規約
# --------------------------------------------------------------------------


class PointFieldSpec(ShasouModel):
    """PointCloud2 の 1 フィールドの規約。"""

    name: str
    datatype: str = Field(description="float32 / uint8 / uint16 等")
    required: bool = True
    description: str = ""


# LiDAR: deskew は下流の責務。センサフレームで格納。
LIDAR_POINT_FIELDS: list[PointFieldSpec] = [
    PointFieldSpec(name="x", datatype="float32", description="センサフレーム X (前)"),
    PointFieldSpec(name="y", datatype="float32", description="センサフレーム Y (左)"),
    PointFieldSpec(name="z", datatype="float32", description="センサフレーム Z (上)"),
    PointFieldSpec(name="intensity", datatype="float32"),
    PointFieldSpec(
        name="ring", datatype="uint16", required=False,
        description="レーザー ID。無い場合は垂直角から算出して付与",
    ),
]

# RADAR: 生の相対動径速度のみ必須。接近が負。自車運動補償 (vx_comp 相当) は
# 下流 (エクスポータ) の責務。RCS/dynprop 等は optional。
RADAR_POINT_FIELDS: list[PointFieldSpec] = [
    PointFieldSpec(name="x", datatype="float32", description="センサフレーム X"),
    PointFieldSpec(name="y", datatype="float32", description="センサフレーム Y"),
    PointFieldSpec(name="z", datatype="float32", description="センサフレーム Z"),
    PointFieldSpec(
        name="velocity_radial", datatype="float32",
        description="生の相対動径速度。接近が負。自車運動補償は下流の責務",
    ),
    PointFieldSpec(name="rcs", datatype="float32", required=False,
                   description="レーダ反射断面積 (実車のみ)"),
    PointFieldSpec(name="dynprop", datatype="uint8", required=False,
                   description="動的/静的分類 (実車のみ)"),
]

# --------------------------------------------------------------------------
# JointState (pedals) 正規 name 配列
# --------------------------------------------------------------------------
# position フィールドに踏み込み量 [0,1] を入れる。name 配列はこの順・この綴りに
# 固定し、recorder/studio が完全一致検証する。
PEDAL_JOINT_NAMES: tuple[str, ...] = ("throttle_pedal", "brake_pedal")

# --------------------------------------------------------------------------
# QoS 規約
# --------------------------------------------------------------------------
# DDS は publisher と subscriber の QoS が両立しないと接続しない。publisher 側
# (CARLA ブリッジ・実車ドライバ) の設定を契約として明記し、recorder の
# subscriber がこれに合わせる。core は ROS 非依存なので rclpy.qos.QoSProfile は
# 使わず文字列 enum で表現し、recorder 側のアダプタが rclpy 型へ変換する。


class QosReliability(str, Enum):
    RELIABLE = "reliable"
    BEST_EFFORT = "best_effort"


class QosHistory(str, Enum):
    KEEP_LAST = "keep_last"
    KEEP_ALL = "keep_all"


class QosDurability(str, Enum):
    VOLATILE = "volatile"
    TRANSIENT_LOCAL = "transient_local"


class QosProfile(FrozenModel):
    """トピックの QoS 設定。値型なので不変 (契約の既定値として共有される)。"""

    reliability: QosReliability = QosReliability.RELIABLE
    history: QosHistory = QosHistory.KEEP_LAST
    depth: int = Field(default=10, ge=1, description="history=keep_last のキュー長")
    durability: QosDurability = QosDurability.VOLATILE


# 通常のトピック (センサ・GT・車両状態) はすべてこの既定を使う。
DEFAULT_QOS = QosProfile()

# 静的 tf は「late joiner が後から購読しても最後の 1 通を受け取れる」必要がある
# ため transient_local + depth=1。tf_static 専用の例外。
TRANSIENT_LOCAL_QOS = QosProfile(depth=1, durability=QosDurability.TRANSIENT_LOCAL)

# --------------------------------------------------------------------------
# トピック契約
# --------------------------------------------------------------------------


class TopicRole(str, Enum):
    """トピックの役割。ソース別セットの判定に使う。"""

    SENSOR = "sensor"          # 実センサ。実車・CARLA 共通
    VEHICLE = "vehicle"        # 車両状態 (CAN 相当)。共通
    GROUND_TRUTH = "gt"        # 特権情報。CARLA (シミュレーション) のみ
    SIM_ONLY = "sim_only"      # /clock 等シミュレーション基盤
    REAL_ONLY = "real_only"    # GNSS 生観測・生 CAN 等、実車のみ


class TopicContract(ShasouModel):
    """1 トピック (または名前空間パターン) の契約。"""

    key: str = Field(description="論理キー (channel 名または固定名)")
    ros_type: RosType
    modality: Modality
    role: TopicRole
    frame_id: str | None = Field(
        default=None,
        description="期待される header.frame_id。None は文脈依存または frame なし",
    )
    point_fields: list[PointFieldSpec] | None = None
    per_channel: bool = Field(
        default=False,
        description="True の場合 sensor_config の各チャネルに対して 1 トピック存在",
    )
    required_names: tuple[str, ...] | None = Field(
        default=None, description="JointState の name 配列など固定語彙"
    )
    qos: QosProfile = Field(
        default=DEFAULT_QOS,
        description="publisher 側の QoS。subscriber はこれに合わせる",
    )
    recorded: bool = Field(
        default=True,
        description=(
            "bag への記録対象か。False は「契約として存在は認知するが録らない」"
            "トピック (publish はされるので購読は可能)"
        ),
    )
    notes: str = ""


# --- 共通センサ (実車・CARLA 両方) ------------------------------------------

CAMERA_IMAGE = TopicContract(
    key="camera_image",
    ros_type=RosType.COMPRESSED_IMAGE,
    modality=Modality.CAMERA,
    role=TopicRole.SENSOR,
    per_channel=True,
    frame_id="<channel>_optical",
    notes="名前空間 <ns>/cam_<pos>/image_raw/compressed。frame_id は光学フレーム",
)
CAMERA_INFO = TopicContract(
    key="camera_info",
    ros_type=RosType.CAMERA_INFO,
    modality=Modality.CAMERA,
    role=TopicRole.SENSOR,
    per_channel=True,
    frame_id="<channel>_optical",
    notes="<ns>/cam_<pos>/camera_info。image_raw と同一名前空間",
)
LIDAR_POINTS = TopicContract(
    key="lidar_points",
    ros_type=RosType.POINT_CLOUD2,
    modality=Modality.LIDAR,
    role=TopicRole.SENSOR,
    per_channel=True,
    frame_id="<channel>",
    point_fields=LIDAR_POINT_FIELDS,
    notes="センサフレーム。無補正 (deskew は下流)",
)
RADAR_POINTS = TopicContract(
    key="radar_points",
    ros_type=RosType.POINT_CLOUD2,
    modality=Modality.RADAR,
    role=TopicRole.SENSOR,
    per_channel=True,
    frame_id="<channel>",
    point_fields=RADAR_POINT_FIELDS,
)
IMU_DATA = TopicContract(
    key="imu",
    ros_type=RosType.IMU,
    modality=Modality.IMU,
    role=TopicRole.SENSOR,
    frame_id="imu_link",
    notes="orientation は無効 (covariance[0]=-1)。生センサとして扱う",
)
GNSS_FIX = TopicContract(
    key="gnss_fix",
    ros_type=RosType.NAV_SAT_FIX,
    modality=Modality.GNSS,
    role=TopicRole.SENSOR,
    frame_id="gnss_link",
)

# --- 車両状態 (共通) --------------------------------------------------------

VEHICLE_DRIVE_STATE = TopicContract(
    key="vehicle_drive_state",
    ros_type=RosType.ACKERMANN_DRIVE_STAMPED,
    modality=Modality.VEHICLE,
    role=TopicRole.VEHICLE,
    frame_id="base_link",
    notes="speed=m/s(後退負), steering_angle=rad(左正・前輪実舵角)",
)
VEHICLE_PEDALS = TopicContract(
    key="vehicle_pedals",
    ros_type=RosType.JOINT_STATE,
    modality=Modality.VEHICLE,
    role=TopicRole.VEHICLE,
    required_names=PEDAL_JOINT_NAMES,
    notes="position に踏み込み量 [0,1]。name は PEDAL_JOINT_NAMES に固定",
)
VEHICLE_REVERSE = TopicContract(
    key="vehicle_reverse", ros_type=RosType.BOOL,
    modality=Modality.VEHICLE, role=TopicRole.VEHICLE,
)
VEHICLE_HANDBRAKE = TopicContract(
    key="vehicle_handbrake", ros_type=RosType.BOOL,
    modality=Modality.VEHICLE, role=TopicRole.VEHICLE,
)

# --- イベントタグ (共通) ----------------------------------------------------

EVENTS = TopicContract(
    key="events",
    ros_type=RosType.EVENT_TAG,
    modality=Modality.VEHICLE,
    role=TopicRole.SENSOR,
    notes="events.jsonl はこのトピックからの派生物 (正は bag 側)",
)

# --- CARLA 特権情報 (Ground Truth) ------------------------------------------

GT_EGO_ODOM = TopicContract(
    key="gt_ego_odom",
    ros_type=RosType.ODOMETRY,
    modality=Modality.VEHICLE,
    role=TopicRole.GROUND_TRUTH,
    frame_id="map",
    notes="pose=map, twist=base_link (child_frame)。trajectory 成果物の源泉",
)
GT_OBJECTS = TopicContract(
    key="gt_objects",
    ros_type=RosType.POINT_CLOUD2,  # 実体は独自 Detection3DArray 拡張
    modality=Modality.VEHICLE,
    role=TopicRole.GROUND_TRUTH,
    frame_id="map",
    notes="全アクターの 3D BBox・actor_id・クラス・速度。map 座標。型は shasou_msgs",
)
GT_AGENT_PLAN = TopicContract(
    key="gt_agent_plan",
    ros_type=RosType.PATH,
    modality=Modality.VEHICLE,
    role=TopicRole.GROUND_TRUTH,
    frame_id="map",
    notes="PDM-Lite の計画軌跡。E2E 学習資産",
)
GT_OBJECT_ATTRIBUTES = TopicContract(
    key="gt_object_attributes",
    ros_type=RosType.STRING,
    modality=Modality.VEHICLE,
    role=TopicRole.GROUND_TRUTH,
    recorded=False,
    notes=(
        "<ns>/gt/object_attributes。JSON ペイロード。CARLA ブリッジが将来の拡張余地"
        "として publish するが記録しない: visibility 等は studio の変換パイプラインが"
        "オフライン算出する方針のため"
    ),
)
GT_DEPTH_IMAGE = TopicContract(
    key="gt_depth_image",
    ros_type=RosType.IMAGE,
    modality=Modality.CAMERA,
    role=TopicRole.GROUND_TRUTH,
    per_channel=True,
    frame_id="<channel>_optical",
    notes="<ns>/gt/depth_<pos>/image。32FC1 メートル深度。RGB と光学フレーム共有",
)

# --- 基盤 -------------------------------------------------------------------

CLOCK = TopicContract(
    key="clock",
    ros_type=RosType.CLOCK,
    modality=Modality.VEHICLE,
    role=TopicRole.SIM_ONLY,
    notes="CARLA のシミュレーション時刻。実車では存在しない",
)
TF_STATIC = TopicContract(
    key="tf_static",
    ros_type=RosType.TF_MESSAGE,
    modality=Modality.VEHICLE,
    role=TopicRole.SENSOR,
    qos=TRANSIENT_LOCAL_QOS,
    notes="base_link -> 各センサの外部パラメータ。動的 tf は記録しない",
)
TF_DYNAMIC = TopicContract(
    key="tf",
    ros_type=RosType.TF_MESSAGE,
    modality=Modality.VEHICLE,
    role=TopicRole.SENSOR,
    recorded=False,
    notes=(
        "動的 tf (map -> base_link)。publish はされるが記録しない: gt/ego_odom と "
        "情報が重複し、リプレイ時の tf 時刻補間問題を持ち込むため (frames.py 参照)。"
        "ego pose の正はトピック / trajectory 成果物"
    ),
)

# --------------------------------------------------------------------------
# ソース別トピックセット
# --------------------------------------------------------------------------

ALL_CONTRACTS: list[TopicContract] = [
    CAMERA_IMAGE, CAMERA_INFO, LIDAR_POINTS, RADAR_POINTS, IMU_DATA, GNSS_FIX,
    VEHICLE_DRIVE_STATE, VEHICLE_PEDALS, VEHICLE_REVERSE, VEHICLE_HANDBRAKE,
    EVENTS, TF_STATIC, TF_DYNAMIC,
    GT_EGO_ODOM, GT_OBJECTS, GT_AGENT_PLAN, GT_OBJECT_ATTRIBUTES, GT_DEPTH_IMAGE,
    CLOCK,
]


def contracts_for_source(
    source: DataSource, *, recorded_only: bool = False
) -> list[TopicContract]:
    """指定ソースで存在しうるトピック契約の一覧を返す。

    - CARLA: 共通センサ + 車両 + GT + 基盤。REAL_ONLY は除外
    - REAL:  共通センサ + 車両。GROUND_TRUTH / SIM_ONLY は除外

    既定では recorded=False の契約 (publish はされるが録らないもの) も含む。
    「bag に存在すべきトピック」を得たい場合は recorded_only=True を指定する。
    """
    result: list[TopicContract] = []
    for c in ALL_CONTRACTS:
        if source == DataSource.CARLA and c.role == TopicRole.REAL_ONLY:
            continue
        if source == DataSource.REAL and c.role in (
            TopicRole.GROUND_TRUTH, TopicRole.SIM_ONLY
        ):
            continue
        if recorded_only and not c.recorded:
            continue
        result.append(c)
    return result


def resolve_topic_name(namespace: str, channel: str, contract: TopicContract) -> str:
    """契約とチャネルから、規約上の期待トピック名を組み立てる (検証補助)。

    実際のトピック名の正は manifest の sensor_config。これは規約側の期待値。
    """
    ns = namespace.rstrip("/")
    if contract.key == "camera_image":
        return f"{ns}/{channel.lower()}/image_raw/compressed"
    if contract.key == "camera_info":
        return f"{ns}/{channel.lower()}/camera_info"
    if contract.key == "gt_depth_image":
        return f"{ns}/gt/depth_{channel.lower()}/image"
    if contract.per_channel:
        return f"{ns}/{channel.lower()}/points"
    return f"{ns}/{contract.key}"


DEFAULT_NAMESPACE = TOPIC_NAMESPACE
