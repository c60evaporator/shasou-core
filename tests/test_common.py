import pytest
from pydantic import TypeAdapter, ValidationError

from shasou_core import (
    Pose,
    QuaternionXYZW,
    Token,
    Vector3,
    derived_token,
    new_token,
    ns_to_us,
    seconds_to_ns,
)

token_adapter = TypeAdapter(Token)


class TestToken:
    def test_new_token_matches_pattern(self):
        token_adapter.validate_python(new_token())

    def test_derived_token_is_deterministic(self):
        a = derived_token("track123", "scene456")
        b = derived_token("track123", "scene456")
        assert a == b
        token_adapter.validate_python(a)

    def test_derived_token_differs_by_input(self):
        assert derived_token("a", "b") != derived_token("a", "c")
        # 区切りの曖昧さがないこと ("ab"+"c" と "a"+"bc" は別)
        assert derived_token("ab", "c") != derived_token("a", "bc")

    def test_invalid_token_rejected(self):
        with pytest.raises(ValidationError):
            token_adapter.validate_python("XYZ")  # 大文字・短すぎ


class TestTime:
    def test_carla_elapsed_seconds(self):
        # 例の nanosec バグの再発防止: 19.283 秒は 19_283_000_000 ns
        assert seconds_to_ns(19.283) == 19_283_000_000

    def test_ns_to_us_truncates(self):
        assert ns_to_us(19_283_000_999) == 19_283_000


class TestQuaternion:
    def test_identity_is_valid(self):
        q = QuaternionXYZW.identity()
        assert q.w == 1.0

    def test_unnormalized_rejected(self):
        with pytest.raises(ValidationError):
            QuaternionXYZW(x=0.0, y=0.0, z=0.0, w=2.0)

    def test_normalized_helper(self):
        q = QuaternionXYZW(x=0.0, y=0.0, z=0.0005, w=1.0)  # 誤差 1e-3 以内は許容
        qn = q.normalized()
        assert abs(qn.x**2 + qn.y**2 + qn.z**2 + qn.w**2 - 1.0) < 1e-12


class TestRoundtrip:
    def test_pose_json_roundtrip(self):
        pose = Pose(
            translation=Vector3(x=1.0, y=-2.5, z=0.3),
            rotation=QuaternionXYZW.identity(),
        )
        restored = Pose.model_validate_json(pose.model_dump_json())
        assert restored == pose

    def test_extra_fields_forbidden(self):
        with pytest.raises(ValidationError):
            Vector3.model_validate({"x": 0, "y": 0, "z": 0, "unknown": 1})
