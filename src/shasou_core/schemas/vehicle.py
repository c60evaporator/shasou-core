"""車種 (VehicleType) と車両個体 (Vehicle) の定義スキーマ。

フリート運用 (同一 platform に複数の車両個体) を表現するため、車種の物理
パラメータ (VehicleType) と、その車種に属する個体 (Vehicle) を分離する。
platform は「センサ構成 (sensor_rig) + 車種 (vehicle_type)」の宣言であり、
そこに複数の Vehicle がぶら下がる。

責務分担:
- VehicleType: 車種としての公称物理パラメータと CAN 仕様のデフォルト。
  studio が編集元 (source of truth)。
- Vehicle: 車両個体。core が持つのは最小限 (所属 platform と CAN 仕様の
  個体差のみ)。運用管理情報 (稼働状態・所在等) は studio の責務。
- CAN 仕様の実効値は「車種デフォルト (can_defaults) を個体の上書き
  (can_overrides) がフィールド単位で覆う」ことで求める (effective_can_spec)。

CanSpec の語彙 (SpeedSignRule / BrakeNormalization) はこのファイルが定義元。
移設前は platform.py にあったが、唯一の消費者が CanSpec になったため消費者の
隣へ置く (platform.py はこれらを参照しない)。
"""

from __future__ import annotations

import math
from enum import Enum
from typing import Optional

from pydantic import Field

from .common import ShasouModel, Vector3

# --------------------------------------------------------------------------
# CAN 仕様の語彙
# --------------------------------------------------------------------------


class SpeedSignRule(str, Enum):
    """ソース (CAN / CARLA) の速度値の符号規則。

    shasou の契約は「m/s・後退で負」(constants.py)。ソースがこの契約と
    異なる場合にアダプタがどう変換すべきかを宣言する。
    """

    SIGNED = "signed"  # ソース速度が符号付き (後退で負)。そのまま使える
    ABS_WITH_REVERSE_FLAG = "abs_with_reverse_flag"  # 速度は常に非負。reverse フラグで符号を付与


class BrakeNormalization(str, Enum):
    """pedals トピックの brake=1.0 が何を意味するか。"""

    STROKE = "stroke"  # 最大ペダルストロークを 1.0 とする
    PRESSURE = "pressure"  # 最大ブレーキ液圧を 1.0 とする
    SWITCH = "switch"  # ブレーキスイッチ。0/1 の二値のみ


class CanSpec(ShasouModel):
    """CAN 由来の車両状態トピックの解釈規約。

    車種デフォルト (VehicleType.can_defaults) と個体上書き (Vehicle.can_overrides)
    の両方で使う。どちらも手書きされうるため各フィールドは optional。実効値の
    合成は overlay() が担う。
    """

    speed_sign_rule: Optional[SpeedSignRule] = Field(
        default=None,
        description="ソース速度の符号規則。契約 (m/s・後退負) への変換方法",
    )
    brake_normalization: Optional[BrakeNormalization] = Field(
        default=None,
        description="pedals トピックの brake=1.0 の定義",
    )

    def overlay(self, base: "CanSpec | None") -> "CanSpec":
        """self の非 None フィールドで base を上書きした実効 CanSpec を返す。

        フィールド単位で「override (self) → default (base) → 未定義 (None)」に
        畳む。両方 None の項目は未定義のまま残り、それを必要とするアダプタが
        その時点でエラーにする。フィールドを足しても壊れない形。
        """
        base = base or CanSpec()
        return CanSpec(
            speed_sign_rule=(
                self.speed_sign_rule
                if self.speed_sign_rule is not None
                else base.speed_sign_rule
            ),
            brake_normalization=(
                self.brake_normalization
                if self.brake_normalization is not None
                else base.brake_normalization
            ),
        )


# --------------------------------------------------------------------------
# 車種
# --------------------------------------------------------------------------


class VehicleDimensions(ShasouModel):
    """車両の外形寸法 [m]。混合学習時に車格の近さを判断する材料。

    ブロックを宣言する場合は 3 値そろえる (部分的な寸法宣言は意味を持たない)。
    ブロック自体は VehicleType 側で optional。
    """

    length_m: float = Field(gt=0, description="全長 [m]")
    width_m: float = Field(gt=0, description="全幅 [m]")
    height_m: float = Field(gt=0, description="全高 [m]")


class VehicleType(ShasouModel):
    """車種の公称物理パラメータ。studio が編集元。

    platform 定義同様に手書きされうるため、識別子以外はすべて optional。
    値が無いパラメータを必要とするアダプタは、その時点でエラーにする。
    """

    vehicle_type_id: str = Field(description="車種の識別子 (例 'lincoln_mkz')")
    steering_gear_ratio: Optional[float] = Field(
        default=None, gt=0,
        description="ハンドル角→前輪実舵角の変換比 (実舵角 = ハンドル角 / ratio)。"
        "角度は rad・左転舵正",
    )
    max_steer_angle_rad: Optional[float] = Field(
        default=None, gt=0, le=math.pi,
        description="最大前輪実舵角 [rad]。CARLA 正規化 steer [-1,1] → rad 変換用",
    )
    wheelbase_m: Optional[float] = Field(
        default=None, gt=0,
        description="ホイールベース [m]。運動学計算と混合学習の判断材料",
    )
    dimensions: Optional[VehicleDimensions] = Field(
        default=None,
        description="外形寸法。混合学習時の車格判断材料",
    )
    base_link_offset: Optional[Vector3] = Field(
        default=None,
        description="車両モデル原点→後軸中心のオフセット [m]。右手系",
    )
    can_defaults: Optional[CanSpec] = Field(
        default=None,
        description="車種としての CAN 仕様デフォルト。個体が上書きしうる",
    )


# --------------------------------------------------------------------------
# 車両個体
# --------------------------------------------------------------------------


class Vehicle(ShasouModel):
    """車両個体。core は最小限に留め、運用管理情報は studio の責務。

    車種は所属 platform 経由で解決する (Vehicle → Platform.vehicle_type →
    VehicleType)。個体固有なのは所属 platform と CAN 仕様の個体差のみ。
    """

    vehicle_id: str = Field(description="車両個体の識別子")
    platform_id: str = Field(description="所属 platform の ID")
    can_overrides: Optional[CanSpec] = Field(
        default=None,
        description="車種デフォルトへのフィールド単位の上書き。None の項目は "
        "車種デフォルトにフォールバックする",
    )

    def effective_can_spec(self, vehicle_type: VehicleType) -> CanSpec:
        """この個体の実効 CAN 仕様を求める。

        個体の can_overrides の非 None フィールドが車種の can_defaults を覆い、
        両方 None の項目は未定義のまま残る。vehicle_type は platform 経由で
        呼び出し側が解決して渡す (Vehicle は VehicleType を直接持たない)。
        """
        overrides = self.can_overrides or CanSpec()
        return overrides.overlay(vehicle_type.can_defaults)
