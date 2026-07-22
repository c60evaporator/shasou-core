#!/usr/bin/env python3
"""全トップレベルスキーマの JSON Schema を生成する。

生成物 (jsonschema/<version>/*.schema.json) はコミット対象だが、手で編集しては
ならない (CLAUDE.md §1.3)。CI は --check で「生成し直して差分ゼロ」を検証する。

使い方:
    python scripts/export_jsonschema.py           # 生成 (上書き)
    python scripts/export_jsonschema.py --check   # 差分があれば非ゼロ終了

出力の決定性
------------
CI の差分ゼロ検証が成立する前提として、同じコードからは常にバイト単位で同一の
出力になる必要がある。そのため sort_keys=True で辞書順を固定し、indent=2 /
ensure_ascii=False / 末尾改行 1 つに揃える。model_json_schema() の出力は
そのまま整形するだけで、手を加えない。
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Type

from pydantic import BaseModel

from shasou_core.schemas.calibration import CalibrationSet
from shasou_core.schemas.events import EventTag
from shasou_core.schemas.health import TopicStats
from shasou_core.schemas.manifest import DriveManifest
from shasou_core.schemas.platform import Platform
from shasou_core.schemas.trajectory import TrajectoryMetadata
from shasou_core.schemas.vehicle import Vehicle, VehicleType

# JSON Schema ディレクトリの世代番号。SemVer の MAJOR とは別概念なので連動させない
# (0.x は「初期開発中」を表すだけで、契約の世代は v1)。
# 運用規則: 0.x の間は v1 のまま。破壊的変更で MAJOR が 2 以上になったら v2 を切る。
SCHEMA_DIR = "v1"

# 生成対象。スキーマを追加したらここに 1 行足す (網羅性は test_jsonschema.py が検証)。
EXPORTS: tuple[tuple[Type[BaseModel], str], ...] = (
    (DriveManifest, "drive_manifest.schema.json"),
    (Platform, "platform.schema.json"),
    (VehicleType, "vehicle_type.schema.json"),
    (Vehicle, "vehicle.schema.json"),
    (CalibrationSet, "calibration_set.schema.json"),
    (TrajectoryMetadata, "trajectory_metadata.schema.json"),
    (EventTag, "event_tag.schema.json"),
    (TopicStats, "topic_stats.schema.json"),
)

REPO_ROOT = Path(__file__).resolve().parent.parent
OUTPUT_DIR = REPO_ROOT / "jsonschema" / SCHEMA_DIR


def render(model: Type[BaseModel]) -> str:
    """1 スキーマ分の JSON Schema を決定的な文字列として組み立てる。"""
    return (
        json.dumps(
            model.model_json_schema(),
            sort_keys=True,
            indent=2,
            ensure_ascii=False,
        )
        + "\n"
    )


def write_all(output_dir: Path = OUTPUT_DIR) -> list[Path]:
    output_dir.mkdir(parents=True, exist_ok=True)
    written = []
    for model, filename in EXPORTS:
        path = output_dir / filename
        path.write_text(render(model), encoding="utf-8")
        written.append(path)
    return written


def check_all(output_dir: Path = OUTPUT_DIR) -> list[str]:
    """生成物とコードのズレを列挙する。空リストなら差分ゼロ。"""
    problems = []
    for model, filename in EXPORTS:
        path = output_dir / filename
        if not path.exists():
            problems.append(f"{filename}: 生成物が存在しない")
        elif path.read_text(encoding="utf-8") != render(model):
            problems.append(f"{filename}: コードと差分あり")

    expected = {filename for _, filename in EXPORTS}
    if output_dir.exists():
        for path in sorted(output_dir.glob("*.schema.json")):
            if path.name not in expected:
                problems.append(f"{path.name}: EXPORTS に無い余分な生成物")
    return problems


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    parser.add_argument(
        "--check", action="store_true",
        help="生成せず、コミット済みの生成物と突き合わせる (差分があれば終了コード 1)",
    )
    args = parser.parse_args(argv)

    if args.check:
        problems = check_all()
        if problems:
            print("JSON Schema の生成物がコードと一致しません:", file=sys.stderr)
            for p in problems:
                print(f"  - {p}", file=sys.stderr)
            print(
                "\n`python scripts/export_jsonschema.py` で再生成してください。",
                file=sys.stderr,
            )
            return 1
        print(f"OK: {len(EXPORTS)} 件の JSON Schema はコードと一致しています。")
        return 0

    for path in write_all():
        print(f"wrote {path.relative_to(REPO_ROOT)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
