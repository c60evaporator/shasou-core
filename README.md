# shasou-core

[![CI](https://github.com/c60evaporator/shasou-core/actions/workflows/ci.yml/badge.svg)](https://github.com/c60evaporator/shasou-core/actions/workflows/ci.yml)

shasou (車窓, *shasō*) エコシステムの共有スキーマと規約。

- **規律**: ランタイム依存は pydantic のみ。フレームワーク依存の追加は禁止 (CONTRIBUTING.md 参照)
- 単位規約・チャネル名: `constants.py` / フレーム規約: `frames.py`
- スキーマバージョン: `version.py` (データ契約の SemVer)
- JSON Schema: `jsonschema/v1/` (生成物。手で編集せず `scripts/export_jsonschema.py` で再生成)

```bash
pip install -e ".[dev,io]"                     # 開発セットアップ (io は Parquet 読み書き用)
pytest                                          # 全テスト

python scripts/export_jsonschema.py             # JSON Schema 再生成
python scripts/export_jsonschema.py --check     # 生成物がコードと一致するか (CI と同じ検証)
```

依存規律 (core 本体は pydantic のみ) の検証は、io extra を入れない環境で行う:

```bash
pip install -e ".[dev]"                  # io extra を入れない
python scripts/check_dependencies.py
```
