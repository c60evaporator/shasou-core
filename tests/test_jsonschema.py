"""コミット済み JSON Schema がコードと一致することの検証。

CLAUDE.md §1.3「生成物はコミットするが手で書かない。CI で生成し直して差分ゼロを
検証する」の中身。CI 設定は別タスクだが、検証ロジック自体はここに持たせる。
"""

import importlib.util
import json
from pathlib import Path

import pytest

REPO_ROOT = Path(__file__).resolve().parent.parent
SCRIPT_PATH = REPO_ROOT / "scripts" / "export_jsonschema.py"

# scripts/ は package ではないのでパス指定でロードする
_spec = importlib.util.spec_from_file_location("export_jsonschema", SCRIPT_PATH)
export_jsonschema = importlib.util.module_from_spec(_spec)
_spec.loader.exec_module(export_jsonschema)

EXPORTS = export_jsonschema.EXPORTS
OUTPUT_DIR = export_jsonschema.OUTPUT_DIR

_REGENERATE = "`python scripts/export_jsonschema.py` で再生成してください"

# 期待するファイル名。スキーマを足して export し忘れたら落ちるトリップワイヤ。
EXPECTED_FILENAMES = {
    "drive_manifest.schema.json",
    "platform.schema.json",
    "vehicle_type.schema.json",
    "vehicle.schema.json",
    "calibration_set.schema.json",
    "trajectory_metadata.schema.json",
    "event_tag.schema.json",
    "topic_stats.schema.json",
}


@pytest.mark.parametrize(
    "model,filename", EXPORTS, ids=[f for _, f in EXPORTS]
)
class TestCommittedSchemasMatchCode:
    def test_file_exists(self, model, filename):
        assert (OUTPUT_DIR / filename).exists(), f"{filename} が無い。{_REGENERATE}"

    def test_matches_model(self, model, filename):
        committed = (OUTPUT_DIR / filename).read_text(encoding="utf-8")
        assert committed == export_jsonschema.render(model), (
            f"{filename} がコードと一致しない (手編集または再生成漏れ)。{_REGENERATE}"
        )


class TestDeterminism:
    @pytest.mark.parametrize("model", [m for m, _ in EXPORTS])
    def test_render_is_stable(self, model):
        # 差分ゼロ検証はこの決定性が前提
        assert export_jsonschema.render(model) == export_jsonschema.render(model)

    @pytest.mark.parametrize("filename", sorted(EXPECTED_FILENAMES))
    def test_formatting_convention(self, filename):
        text = (OUTPUT_DIR / filename).read_text(encoding="utf-8")
        assert text.endswith("\n") and not text.endswith("\n\n"), "末尾改行は 1 つ"
        # sort_keys=True / indent=2 で書き直しても同じ = 整形規約が守られている
        assert text == json.dumps(
            json.loads(text), sort_keys=True, indent=2, ensure_ascii=False
        ) + "\n"


class TestCoverage:
    def test_export_count_matches_files_on_disk(self):
        on_disk = {p.name for p in OUTPUT_DIR.glob("*.schema.json")}
        assert len(EXPORTS) == len(on_disk)
        assert {f for _, f in EXPORTS} == on_disk

    def test_expected_top_level_schemas(self):
        # トップレベルスキーマを追加したらここも更新する (意識的な更新を強制)
        assert {f for _, f in EXPORTS} == EXPECTED_FILENAMES

    def test_filenames_unique(self):
        assert len({f for _, f in EXPORTS}) == len(EXPORTS)


class TestCheckMode:
    def test_check_passes_on_committed_state(self):
        assert export_jsonschema.check_all() == []

    def test_check_detects_drift(self, tmp_path):
        # 生成物が壊れている状態を検出できること (--check の検出力)
        model, filename = EXPORTS[0]
        (tmp_path / filename).write_text('{"broken": true}\n', encoding="utf-8")
        problems = export_jsonschema.check_all(tmp_path)
        assert any(filename in p and "差分" in p for p in problems)

    def test_check_detects_missing_file(self, tmp_path):
        problems = export_jsonschema.check_all(tmp_path)
        assert len(problems) == len(EXPORTS)
        assert all("存在しない" in p for p in problems)

    def test_check_detects_extra_file(self, tmp_path):
        for model, filename in EXPORTS:
            (tmp_path / filename).write_text(
                export_jsonschema.render(model), encoding="utf-8")
        (tmp_path / "stale.schema.json").write_text("{}\n", encoding="utf-8")
        problems = export_jsonschema.check_all(tmp_path)
        assert any("stale.schema.json" in p and "余分" in p for p in problems)


class TestSchemaContent:
    """生成物が JSON Schema として最低限まともであることの確認。"""

    @pytest.mark.parametrize("filename", sorted(EXPECTED_FILENAMES))
    def test_parses_and_has_properties(self, filename):
        schema = json.loads((OUTPUT_DIR / filename).read_text(encoding="utf-8"))
        assert schema["type"] == "object"
        assert schema["properties"]
