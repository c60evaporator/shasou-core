"""スキーマバージョン定義。

SCHEMA_VERSION はデータ契約 (manifest / trajectory / topics 規約) のバージョンで、
SemVer に従う。パッケージバージョン (pyproject.toml) とは独立に管理する:
コードのリファクタリングではパッケージ版のみ上がり、契約の変更では両方上がる。

- MAJOR: 後方非互換なスキーマ変更 (フィールド削除・意味変更・単位変更)
- MINOR: 後方互換な追加 (optional フィールド追加、enum 値追加)
- PATCH: ドキュメント・制約の明確化のみ

DriveManifest は自身が書かれた時点の SCHEMA_VERSION を記録し、
読み手 (studio) は MAJOR 一致を要求する。
"""

SCHEMA_VERSION = "0.1.0"


def major(version: str = SCHEMA_VERSION) -> int:
    """MAJOR 部を返す。互換性判定に使う。"""
    return int(version.split(".", 1)[0])
