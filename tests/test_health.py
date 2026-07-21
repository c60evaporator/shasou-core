import pytest
from pydantic import ValidationError

from shasou_core.schemas.health import DiskStats, TopicStat, TopicStats

_T0 = 1752641234512000000
_T1 = _T0 + 60 * 1_000_000_000  # 60 秒後


def _sensor_stat(**overrides):
    data = dict(
        topic_name="/sensing/lidar_top/points",
        channel="LIDAR_TOP",
        message_count=1200,
        expected_hz=20.0,
        measured_hz=19.8,
        drop_rate=0.01,
        first_timestamp=_T0,
        last_timestamp=_T1,
        max_gap_ns=120_000_000,
    )
    data.update(overrides)
    return data


def _stats(**overrides):
    data = dict(
        drive_id="2026-07-16_1030_vehicle01_osaka-umeda",
        duration_ns=60 * 1_000_000_000,
        stats=[TopicStat(**_sensor_stat())],
    )
    data.update(overrides)
    return data


class TestTopicStat:
    def test_sensor_topic_valid(self):
        s = TopicStat(**_sensor_stat())
        assert s.channel == "LIDAR_TOP"
        assert s.drop_rate == pytest.approx(0.01)

    def test_gt_topic_without_optionals(self):
        # gt 系はチャネルに紐づかず、期待レートも決まっていない
        s = TopicStat(
            topic_name="/shasou/gt/objects",
            message_count=1200,
        )
        assert s.channel is None
        assert s.expected_hz is None
        assert s.drop_rate is None
        assert s.first_timestamp is None

    def test_drop_rate_bounds(self):
        # 境界は通す
        assert TopicStat(**_sensor_stat(drop_rate=0.0)).drop_rate == 0.0
        assert TopicStat(**_sensor_stat(drop_rate=1.0)).drop_rate == 1.0
        for bad in (-0.1, 1.1):
            with pytest.raises(ValidationError):
                TopicStat(**_sensor_stat(drop_rate=bad))

    def test_negative_counts_rejected(self):
        with pytest.raises(ValidationError):
            TopicStat(**_sensor_stat(message_count=-1))
        with pytest.raises(ValidationError):
            TopicStat(**_sensor_stat(max_gap_ns=-1))
        with pytest.raises(ValidationError):
            TopicStat(**_sensor_stat(first_timestamp=-1))

    def test_nonpositive_expected_hz_rejected(self):
        with pytest.raises(ValidationError):
            TopicStat(**_sensor_stat(expected_hz=0.0))
        with pytest.raises(ValidationError):
            TopicStat(**_sensor_stat(expected_hz=-20.0))

    def test_measured_hz_zero_allowed(self):
        # 1 件も来なかったトピックは実測 0 Hz でありうる
        assert TopicStat(**_sensor_stat(measured_hz=0.0)).measured_hz == 0.0

    def test_time_order_enforced(self):
        with pytest.raises(ValidationError):
            TopicStat(**_sensor_stat(first_timestamp=_T1, last_timestamp=_T0))

    def test_invalid_channel_name_rejected(self):
        with pytest.raises(ValidationError):
            TopicStat(**_sensor_stat(channel="lidar_top"))
        with pytest.raises(ValidationError):
            TopicStat(**_sensor_stat(channel="FOO_BAR"))

    def test_observed_duration(self):
        assert TopicStat(**_sensor_stat()).observed_duration_ns() == 60 * 10**9
        # 片方でも欠ければ算出しない
        assert TopicStat(**_sensor_stat(last_timestamp=None)).observed_duration_ns() is None
        assert TopicStat(**_sensor_stat(first_timestamp=None)).observed_duration_ns() is None

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            TopicStat(**_sensor_stat(jitter_ns=100))


class TestDiskStats:
    def test_all_optional(self):
        d = DiskStats()
        assert d.min_free_bytes is None

    def test_negative_rejected(self):
        with pytest.raises(ValidationError):
            DiskStats(min_free_bytes=-1)
        with pytest.raises(ValidationError):
            DiskStats(write_error_count=-1)

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            DiskStats(free_pct=0.5)


class TestTopicStats:
    def test_valid(self):
        s = TopicStats(**_stats())
        assert s.schema_version  # 書き込み時の版が既定で入る
        assert s.disk is None

    def test_with_disk(self):
        s = TopicStats(**_stats(disk=DiskStats(
            min_free_bytes=42_000_000_000,
            total_bytes_written=180_000_000_000,
            write_error_count=0,
        )))
        assert s.disk.write_error_count == 0

    def test_duplicate_topic_rejected(self):
        with pytest.raises(ValidationError):
            TopicStats(**_stats(stats=[
                TopicStat(**_sensor_stat()),
                TopicStat(**_sensor_stat(measured_hz=19.5)),
            ]))

    def test_stat_for(self):
        s = TopicStats(**_stats())
        assert s.stat_for("/sensing/lidar_top/points").channel == "LIDAR_TOP"
        assert s.stat_for("/sensing/nonexistent") is None

    def test_empty_stats_allowed(self):
        # 統計が 1 件も無い (計測が回らなかった) 状態も記録できる
        assert TopicStats(**_stats(stats=[])).stats == []

    def test_negative_duration_rejected(self):
        with pytest.raises(ValidationError):
            TopicStats(**_stats(duration_ns=-1))

    def test_unknown_field_rejected(self):
        with pytest.raises(ValidationError):
            TopicStats(**_stats(cpu_load=0.4))

    def test_json_roundtrip(self):
        s = TopicStats(**_stats(disk=DiskStats(min_free_bytes=42_000_000_000)))
        assert TopicStats.model_validate_json(s.model_dump_json()) == s

    def test_dict_roundtrip(self):
        s = TopicStats(**_stats())
        assert TopicStats.model_validate(s.model_dump()) == s
