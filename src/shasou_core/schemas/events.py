"""イベントタグのスキーマ。

EventTag は events.jsonl の 1 行 (1 イベント) であり、同時に ROS
`shasou_msgs/msg/EventTag` (topics.py の EVENTS 契約) のペイロード契約でもある。
events.jsonl は bag からの派生物で、正は bag 側 (§2.1)。jsonl はいつでも
bag から再生成できる。

人間起点タグと自動タグの共存
----------------------------
収録中に人間が付けるタグ (driver_button / tablet) と、収録後に自動生成される
タグ (carla_scenario / auto_vlm) を 1 つの型で表現し、source で区別する。
両者はフォーマットが同じなので、下流は source を見るだけで来歴を判別できる。

語彙の設計 (閉じた軸と開いた軸)
-------------------------------
- type:   閉じた enum。粗い分類軸で、下流が網羅的に分岐するため固定語彙にする。
          値の追加は SCHEMA_VERSION の更新を伴う
- label:  自由記述。具体性はここが担うので type を粗く保てる。選択式語彙集の
          UI は studio の責務で、core は形式のみ規定する
- source: str 型。将来の収録デバイスや自動タグ生成器の追加が読めないため、
          core を変更せず独自値を足せるようにする。ただし表記揺れを防ぐため
          命名規約 (小文字 snake_case) は強制し、既知値は EventSource に置く
"""

from __future__ import annotations

import re
from enum import Enum

from pydantic import Field, field_validator

from .common import ShasouModel, TimestampNs


class EventType(str, Enum):
    """イベントの分類 (閉じた固定語彙)。具体的な中身は label が持つ。"""

    INTERESTING = "interesting"  # 学習価値の高いシーン (cut-in 等)
    MARKER = "marker"            # 目印・区間境界 (construction zone 等)
    INCIDENT = "incident"        # ヒヤリハット・事故等の安全事象
    TAKEOVER = "takeover"        # 自動運転からの介入・手動復帰
    SYSTEM = "system"            # 収録系の状態変化 (センサ異常等)


class EventSource(str, Enum):
    """既知の source 値。EventTag.source は str なのでこれ以外も指定できる。

    独自の収録デバイスや自動タグ生成器を足す場合は、SOURCE_PATTERN を満たす
    任意の文字列を使ってよい (core の変更は不要)。
    """

    DRIVER_BUTTON = "driver_button"    # 収録中・人間起点 (車内ボタン)
    TABLET = "tablet"                  # 収録中・人間起点 (同乗者タブレット)
    CARLA_SCENARIO = "carla_scenario"  # 収録後・自動 (シナリオ定義由来)
    AUTO_VLM = "auto_vlm"              # 収録後・自動 (VLM による付与)


# source の命名規約。小文字英数字とアンダースコアのみ。表記揺れ
# ("Driver Button" / "DRIVER_BUTTON") を弾いて catalog 検索を効かせる。
SOURCE_PATTERN = re.compile(r"^[a-z][a-z0-9_]*$")


class EventTag(ShasouModel):
    """events.jsonl の 1 行 = 1 イベント。ROS EventTag のペイロードと同一契約。"""

    timestamp: TimestampNs = Field(
        strict=True,
        description="イベント発生時刻 (エポックからの ns 整数)",
    )
    type: EventType
    label: str = Field(
        min_length=1,
        description="具体的な中身 (cut-in / construction zone 等)。自由記述",
    )
    source: str = Field(
        description="誰が付けたか。既知値は EventSource、独自値も可",
    )

    # timestamp だけ strict=True にしてある。素の TimestampNs では整数値の float
    # (1752641234.0) が黙って int に強制変換され、秒を ns 欄に入れる事故が
    # 静かに通ってしまう。events は人間や外部デバイスが書く入口なので、
    # trajectory 系より厳格にして float を全面拒否する。float 秒からの変換は
    # 呼び出し側が constants の seconds_to_ns() を通すこと。

    @field_validator("source", mode="before")
    @classmethod
    def _normalize_source(cls, v: object) -> object:
        # EventSource メンバをそのまま渡せるようにする。Python 3.10 では
        # str(EventSource.TABLET) が "EventSource.TABLET" になるため、
        # ここで .value に正規化しておかないと jsonl に enum 名が漏れる。
        if isinstance(v, Enum):
            return v.value
        return v

    @field_validator("source")
    @classmethod
    def _valid_source(cls, v: str) -> str:
        if not SOURCE_PATTERN.match(v):
            raise ValueError(
                f"source が命名規約違反: {v!r}. "
                "小文字英字で始まり、小文字英数字とアンダースコアのみ許容"
            )
        return v

    @field_validator("label")
    @classmethod
    def _label_not_blank(cls, v: str) -> str:
        if not v.strip():
            raise ValueError("label が空白のみ")
        return v
