import pytest
from pydantic import ValidationError

from shasou_core.schemas.common import seconds_to_ns
from shasou_core.schemas.events import EventSource, EventTag, EventType

# docs/recorder_summary.md の例に対応する時刻 (float 秒 -> ns)
_TS = 1752641234512000000


def _tag(**overrides):
    data = dict(
        timestamp=_TS,
        type=EventType.INTERESTING,
        label="cut-in",
        source=EventSource.DRIVER_BUTTON,
    )
    data.update(overrides)
    return data


class TestHumanAndAutoTags:
    """人間起点タグと自動タグが同じ型で共存できること (§6)。"""

    def test_human_tag(self):
        t = EventTag(**_tag())
        assert t.type == EventType.INTERESTING
        assert t.source == "driver_button"

    def test_auto_tag(self):
        t = EventTag(**_tag(
            type=EventType.MARKER,
            label="construction zone",
            source=EventSource.AUTO_VLM,
        ))
        assert t.source == "auto_vlm"

    def test_same_type_for_both(self):
        human = EventTag(**_tag(source=EventSource.TABLET))
        auto = EventTag(**_tag(source=EventSource.CARLA_SCENARIO))
        assert type(human) is type(auto)
        # 下流は source だけ見れば来歴を判別できる
        assert {human.source, auto.source} == {"tablet", "carla_scenario"}


class TestSource:
    def test_enum_normalized_to_value(self):
        # str(EventSource.TABLET) は "EventSource.TABLET" になるため、
        # .value へ正規化されていないと jsonl に enum 名が漏れる
        t = EventTag(**_tag(source=EventSource.TABLET))
        assert t.source == "tablet"
        assert '"source":"tablet"' in t.model_dump_json()

    def test_custom_source_allowed(self):
        # OSS 利用者が core を変更せず独自デバイスを足せること
        t = EventTag(**_tag(source="my_custom_device"))
        assert t.source == "my_custom_device"

    def test_malformed_source_rejected(self):
        # 表記揺れは弾く (catalog 検索を効かせるため)
        for bad in ("Driver Button", "DRIVER_BUTTON", "driver-button", "1abc", ""):
            with pytest.raises(ValidationError):
                EventTag(**_tag(source=bad))


class TestType:
    def test_string_value_accepted(self):
        t = EventTag(**_tag(type="incident"))
        assert t.type == EventType.INCIDENT

    def test_unknown_type_rejected(self):
        # type は閉じた固定語彙
        with pytest.raises(ValidationError):
            EventTag(**_tag(type="unknown"))


class TestTimestamp:
    def test_ns_integer_accepted(self):
        assert EventTag(**_tag()).timestamp == _TS

    def test_fractional_float_rejected(self):
        with pytest.raises(ValidationError):
            EventTag(**_tag(timestamp=1752641234.512))

    def test_whole_float_rejected(self):
        # 素の TimestampNs だと int に強制変換されて秒が ns 欄に収まってしまう。
        # strict=True でこの穴を塞ぐのが主目的
        with pytest.raises(ValidationError):
            EventTag(**_tag(timestamp=1752641234.0))

    def test_seconds_to_ns_is_the_conversion_path(self):
        # float 秒からの変換は呼び出し側が seconds_to_ns を通す
        t = EventTag(**_tag(timestamp=seconds_to_ns(1752641234.512)))
        assert t.timestamp == _TS

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            EventTag(**_tag(timestamp=-1))


class TestLabelAndExtra:
    def test_blank_label_rejected(self):
        with pytest.raises(ValidationError):
            EventTag(**_tag(label=""))
        with pytest.raises(ValidationError):
            EventTag(**_tag(label="   "))

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            EventTag(**_tag(drive_id="2026-07-16_1030_v01_osaka"))


class TestJsonlRoundTrip:
    def test_jsonl_line_roundtrip(self):
        # events.jsonl の 1 行として読み書きできること
        t = EventTag(**_tag())
        line = t.model_dump_json()
        assert EventTag.model_validate_json(line) == t

    def test_reading_a_jsonl_line(self):
        line = (
            '{"timestamp": 1752641234512000000, "type": "marker", '
            '"label": "construction zone", "source": "tablet"}'
        )
        t = EventTag.model_validate_json(line)
        assert t.type == EventType.MARKER
        assert t.label == "construction zone"

    def test_float_seconds_in_jsonl_rejected(self):
        # docs の例は float 秒。recorder は seconds_to_ns を通す必要がある
        line = '{"timestamp": 1752641234.512, "type": "marker", "label": "x", "source": "tablet"}'
        with pytest.raises(ValidationError):
            EventTag.model_validate_json(line)

    def test_dict_roundtrip(self):
        t = EventTag(**_tag())
        assert EventTag.model_validate(t.model_dump()) == t
