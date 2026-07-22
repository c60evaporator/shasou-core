import math

import pytest
from pydantic import ValidationError

from shasou_core.schemas.common import Vector3
from shasou_core.schemas.vehicle import (
    BrakeNormalization,
    CanSpec,
    SpeedSignRule,
    Vehicle,
    VehicleDimensions,
    VehicleType,
)


class TestCanSpecOverlay:
    def test_override_wins(self):
        base = CanSpec(
            speed_sign_rule=SpeedSignRule.SIGNED,
            brake_normalization=BrakeNormalization.PRESSURE,
        )
        override = CanSpec(speed_sign_rule=SpeedSignRule.ABS_WITH_REVERSE_FLAG)
        eff = override.overlay(base)
        # 非 None の override はデフォルトを覆う
        assert eff.speed_sign_rule == SpeedSignRule.ABS_WITH_REVERSE_FLAG
        # None の override はデフォルトにフォールバック
        assert eff.brake_normalization == BrakeNormalization.PRESSURE

    def test_both_none_stays_undefined(self):
        eff = CanSpec().overlay(CanSpec())
        assert eff.speed_sign_rule is None
        assert eff.brake_normalization is None

    def test_overlay_over_none_base(self):
        override = CanSpec(brake_normalization=BrakeNormalization.SWITCH)
        eff = override.overlay(None)
        assert eff.brake_normalization == BrakeNormalization.SWITCH
        assert eff.speed_sign_rule is None

    def test_field_level_merge(self):
        # 各フィールドが独立にマージされる (どちらか一方だけ埋まる場合)
        base = CanSpec(speed_sign_rule=SpeedSignRule.SIGNED)
        override = CanSpec(brake_normalization=BrakeNormalization.STROKE)
        eff = override.overlay(base)
        assert eff.speed_sign_rule == SpeedSignRule.SIGNED
        assert eff.brake_normalization == BrakeNormalization.STROKE


class TestVehicleEffectiveCanSpec:
    def test_overrides_win_over_defaults(self):
        vt = VehicleType(
            vehicle_type_id="lincoln_mkz",
            can_defaults=CanSpec(
                speed_sign_rule=SpeedSignRule.SIGNED,
                brake_normalization=BrakeNormalization.PRESSURE,
            ),
        )
        v = Vehicle(
            vehicle_id="v07", platform_id="p1",
            can_overrides=CanSpec(brake_normalization=BrakeNormalization.STROKE),
        )
        eff = v.effective_can_spec(vt)
        assert eff.speed_sign_rule == SpeedSignRule.SIGNED       # 車種デフォルト
        assert eff.brake_normalization == BrakeNormalization.STROKE  # 個体上書き

    def test_no_overrides_uses_defaults(self):
        vt = VehicleType(
            vehicle_type_id="lincoln_mkz",
            can_defaults=CanSpec(speed_sign_rule=SpeedSignRule.SIGNED),
        )
        v = Vehicle(vehicle_id="v07", platform_id="p1")
        eff = v.effective_can_spec(vt)
        assert eff.speed_sign_rule == SpeedSignRule.SIGNED

    def test_no_defaults_no_overrides_is_undefined(self):
        vt = VehicleType(vehicle_type_id="lincoln_mkz")
        v = Vehicle(vehicle_id="v07", platform_id="p1")
        eff = v.effective_can_spec(vt)
        assert eff.speed_sign_rule is None
        assert eff.brake_normalization is None


class TestVehicleType:
    def test_minimal(self):
        # 識別子以外はすべて optional (手書き定義を想定)
        vt = VehicleType(vehicle_type_id="lincoln_mkz")
        assert vt.steering_gear_ratio is None
        assert vt.dimensions is None
        assert vt.can_defaults is None

    def test_full(self):
        vt = VehicleType(
            vehicle_type_id="lincoln_mkz",
            steering_gear_ratio=15.7,
            max_steer_angle_rad=0.61,
            wheelbase_m=2.85,
            dimensions=VehicleDimensions(length_m=4.93, width_m=1.86, height_m=1.48),
            base_link_offset=Vector3(x=-1.37, y=0.0, z=-0.32),
            can_defaults=CanSpec(speed_sign_rule=SpeedSignRule.SIGNED),
        )
        assert vt.wheelbase_m == pytest.approx(2.85)
        assert vt.dimensions.length_m == pytest.approx(4.93)
        assert vt.base_link_offset.x == pytest.approx(-1.37)

    def test_nonpositive_ratio_rejected(self):
        with pytest.raises(ValidationError):
            VehicleType(vehicle_type_id="t", steering_gear_ratio=0.0)

    def test_steer_angle_upper_bound(self):
        with pytest.raises(ValidationError):
            VehicleType(vehicle_type_id="t", max_steer_angle_rad=math.pi + 0.1)

    def test_nonpositive_wheelbase_rejected(self):
        with pytest.raises(ValidationError):
            VehicleType(vehicle_type_id="t", wheelbase_m=0.0)

    def test_enums_from_string(self):
        # JSON/YAML からは文字列値で入る
        vt = VehicleType(
            vehicle_type_id="t",
            can_defaults={"speed_sign_rule": "signed", "brake_normalization": "switch"},
        )
        assert vt.can_defaults.speed_sign_rule == SpeedSignRule.SIGNED
        assert vt.can_defaults.brake_normalization == BrakeNormalization.SWITCH

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            VehicleType(vehicle_type_id="t", num_wheels=4)


class TestVehicleDimensions:
    def test_valid(self):
        d = VehicleDimensions(length_m=4.93, width_m=1.86, height_m=1.48)
        assert d.height_m == pytest.approx(1.48)

    def test_all_three_required(self):
        # ブロックを宣言したら 3 値そろえる (部分宣言は無意味)
        with pytest.raises(ValidationError):
            VehicleDimensions(length_m=4.93, width_m=1.86)

    def test_nonpositive_rejected(self):
        with pytest.raises(ValidationError):
            VehicleDimensions(length_m=0.0, width_m=1.86, height_m=1.48)


class TestVehicle:
    def test_minimal(self):
        v = Vehicle(vehicle_id="v07", platform_id="p1")
        assert v.can_overrides is None

    def test_unknown_field_rejected(self):
        # 運用管理情報は studio の責務。core の Vehicle は最小限
        with pytest.raises(ValidationError):
            Vehicle(vehicle_id="v07", platform_id="p1", odometer_km=12000)

    def test_json_roundtrip(self):
        v = Vehicle(
            vehicle_id="v07", platform_id="p1",
            can_overrides=CanSpec(speed_sign_rule=SpeedSignRule.SIGNED),
        )
        restored = Vehicle.model_validate_json(v.model_dump_json())
        assert restored == v

    def test_vehicle_type_roundtrip(self):
        vt = VehicleType(
            vehicle_type_id="lincoln_mkz",
            wheelbase_m=2.85,
            dimensions=VehicleDimensions(length_m=4.93, width_m=1.86, height_m=1.48),
            can_defaults=CanSpec(brake_normalization=BrakeNormalization.STROKE),
        )
        restored = VehicleType.model_validate(vt.model_dump())
        assert restored == vt
