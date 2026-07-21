#!/usr/bin/env python3
"""依存規律の番人 (CLAUDE.md §1.1)。

ランタイム依存は pydantic のみ。I/O 系 (pyarrow 等) は optional extra
`[io]` に隔離されており、core 本体はそれ無しで完全に動かなければならない。
recorder は Jetson 上で動くため、Web アプリ都合の依存が混入すると車載側の
ビルドが汚れる。

このスクリプトは **io extra を入れていない環境** で実行することを前提に、
`shasou_core.io` を除く全サブモジュールを実際に import して確認する。

    pip install -e ".[dev]"        # io extra を入れない
    python scripts/check_dependencies.py

`import shasou_core` だけでは不十分な点に注意: __init__.py は一部のモジュール
しか読み込まないため、validation.py や schemas/platform.py に外部依存が混入
しても素の import では捕まらない。ここでは全モジュールを走査する。
"""

from __future__ import annotations

import importlib
import importlib.util
import pkgutil
import sys

# core 本体が依存してはならないサードパーティ (extras に隔離されているもの)
FORBIDDEN_IN_CORE = ("pyarrow",)

# 依存規律の対象外。ここだけは extras の依存を持ってよい
EXEMPT_PREFIX = "shasou_core.io"


def main() -> int:
    # 禁止依存が入った環境で回すと検証が空振りするので先に弾く
    present = [m for m in FORBIDDEN_IN_CORE if importlib.util.find_spec(m) is not None]
    if present:
        print(
            f"環境に {', '.join(present)} が存在するため依存規律を検証できません。\n"
            'io extra を入れずに `pip install -e ".[dev]"` した環境で実行してください。',
            file=sys.stderr,
        )
        return 1

    import shasou_core

    failures: list[str] = []
    checked = 0
    for module in pkgutil.walk_packages(shasou_core.__path__, "shasou_core."):
        if module.name == EXEMPT_PREFIX or module.name.startswith(EXEMPT_PREFIX + "."):
            continue
        try:
            importlib.import_module(module.name)
        except Exception as exc:  # noqa: BLE001 - 原因を問わず失敗として報告する
            failures.append(f"{module.name}: {type(exc).__name__}: {exc}")
        else:
            checked += 1

    if failures:
        print("core 本体が pydantic 以外に依存しています:", file=sys.stderr)
        for f in failures:
            print(f"  - {f}", file=sys.stderr)
        print(
            "\nI/O 等の外部依存は optional extra に隔離してください (CLAUDE.md §1.1)。",
            file=sys.stderr,
        )
        return 1

    print(f"OK: {checked} モジュールが {', '.join(FORBIDDEN_IN_CORE)} 抜きで読み込めました。")
    return 0


if __name__ == "__main__":
    sys.exit(main())
