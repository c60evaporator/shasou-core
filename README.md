# shasou-core

shasou (車窓, *shasō*) エコシステムの共有スキーマと規約。

- **規律**: ランタイム依存は pydantic のみ。フレームワーク依存の追加は禁止 (CONTRIBUTING.md 参照)
- 単位規約・チャネル名: `constants.py` / フレーム規約: `frames.py`
- スキーマバージョン: `version.py` (データ契約の SemVer)

```bash
pip install -e ".[dev]"
pytest
```
