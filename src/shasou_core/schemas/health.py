"""収録の健全性スキーマ (health/topic_stats.json)。

recorder が収録中に計測した、トピックごとの受信状況を記録する。後から
「この収録は健全だったか」を検証する材料になり、studio の取り込み時の品質
フィルタと recorder のヘルスモニタ表示が参照する。

これも bag からの派生物で、正は bag 側 (§2.1)。統計はいつでも bag から
再計測できるので、ここに記録された値と bag が食い違う場合は bag が正。

単位規約
--------
- 時刻・間隔: エポックからのナノ秒整数 (TimestampNs)。§2 の時刻規約に従う
- レート:     Hz
- 割合:       0.0〜1.0 の float
- サイズ:     バイト

判定を持たない器
----------------
このモジュールは計測値の器に徹し、「健全か否か」の判定は持たない。閾値は
platform や運用で変わるうえ、判定を core に置くと閾値の変更が
SCHEMA_VERSION の更新を伴ってしまう。良否判断は呼び出し側 (recorder の
ヘルスモニタ / studio の取り込みフィルタ) の責務。
"""

from __future__ import annotations

from typing import Optional

from pydantic import Field, field_validator, model_validator

from ..constants import is_valid_channel_name
from ..version import SCHEMA_VERSION
from .common import ShasouModel, TimestampNs


class TopicStat(ShasouModel):
    """1 トピック分の受信統計。

    計測不能な項目は None にする (メッセージ 0 件で平均レートが出せない、
    gt 系で契約上の期待レートが決まっていない、など)。
    """

    topic_name: str = Field(description="実トピック名 (manifest の値と対応)")
    channel: Optional[str] = Field(
        default=None,
        description="対応する正規チャネル名。gt 系・車両状態など、チャネルに"
        "紐づかないトピックは None",
    )
    message_count: int = Field(ge=0, description="受信メッセージ総数")
    expected_hz: Optional[float] = Field(
        default=None, gt=0, description="期待レート [Hz]。不明なら None",
    )
    measured_hz: Optional[float] = Field(
        default=None, ge=0,
        description="実測平均レート [Hz]。0/1 件で算出できなければ None",
    )
    drop_rate: Optional[float] = Field(
        default=None, ge=0, le=1,
        description="推定ドロップ率 (期待に対する取りこぼし割合)。"
        "expected_hz が無ければ算出できず None",
    )
    first_timestamp: Optional[TimestampNs] = Field(
        default=None, description="最初の受信時刻 [ns]。0 件なら None",
    )
    last_timestamp: Optional[TimestampNs] = Field(
        default=None, description="最後の受信時刻 [ns]。0 件なら None",
    )
    max_gap_ns: Optional[int] = Field(
        default=None, ge=0,
        description="最大受信間隔 [ns]。瞬間的な欠落の検出用",
    )

    @field_validator("channel")
    @classmethod
    def _valid_channel(cls, v: Optional[str]) -> Optional[str]:
        if v is not None and not is_valid_channel_name(v):
            raise ValueError(f"チャネル名が命名規約違反: {v!r}")
        return v

    @model_validator(mode="after")
    def _check_time_order(self) -> "TopicStat":
        if (
            self.first_timestamp is not None
            and self.last_timestamp is not None
            and self.last_timestamp < self.first_timestamp
        ):
            raise ValueError("last_timestamp < first_timestamp")
        return self

    def observed_duration_ns(self) -> Optional[int]:
        """最初と最後の受信の間隔 [ns]。どちらか欠けていれば None。"""
        if self.first_timestamp is None or self.last_timestamp is None:
            return None
        return self.last_timestamp - self.first_timestamp


class DiskStats(ShasouModel):
    """収録中のディスク状況。収録失敗の兆候を残す。すべて任意。"""

    min_free_bytes: Optional[int] = Field(
        default=None, ge=0, description="収録中の空き容量の最小値 [bytes]",
    )
    total_bytes_written: Optional[int] = Field(
        default=None, ge=0, description="書き込み総量 [bytes]",
    )
    write_error_count: Optional[int] = Field(
        default=None, ge=0, description="書き込みエラー回数",
    )


class TopicStats(ShasouModel):
    """topic_stats.json 全体。1 ドライブ分の収録健全性。"""

    drive_id: str
    schema_version: str = Field(
        default=SCHEMA_VERSION,
        description="書き込み時の shasou-core スキーマ版",
    )
    duration_ns: int = Field(ge=0, description="収録全体の長さ [ns]")
    stats: list[TopicStat] = Field(description="トピックごとの受信統計")
    disk: Optional[DiskStats] = None

    @field_validator("stats")
    @classmethod
    def _unique_topics(cls, v: list[TopicStat]) -> list[TopicStat]:
        seen: set[str] = set()
        duplicated: set[str] = set()
        for s in v:
            if s.topic_name in seen:
                duplicated.add(s.topic_name)
            seen.add(s.topic_name)
        if duplicated:
            raise ValueError(
                f"同一トピックの統計が重複している: {sorted(duplicated)}"
            )
        return v

    def stat_for(self, topic_name: str) -> Optional[TopicStat]:
        """トピック名で統計を引く。無ければ None。"""
        for s in self.stats:
            if s.topic_name == topic_name:
                return s
        return None
