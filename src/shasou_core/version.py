"""スキーマバージョン定義。

SCHEMA_VERSION はデータ契約 (constants の単位・命名規約、schemas 各種
= manifest / platform / vehicle / calibration / trajectory 等、topics 規約) の
バージョンで、SemVer に従う。パッケージバージョン (pyproject.toml) とは独立に
管理する: コードのリファクタリングではパッケージ版のみ上がり、契約の変更では
両方上がる。

- MAJOR: 後方非互換なスキーマ変更 (フィールド削除・意味変更・単位変更)
- MINOR: 後方互換な追加 (optional フィールド追加、enum 値追加)
- PATCH: ドキュメント・制約の明確化のみ (契約の実体は変わらない)

0.x の間の例外
--------------
MAJOR=0 は「初期開発中」を表す枠で、互換判定 (major()) が MAJOR 一致しか見ない
以上、0.x のうちに MAJOR を上げると全データが即座に非互換になる。そのため
**0.x では MINOR が破壊的変更も担う** (SemVer 一般の慣行と同じ)。1.0.0 以降は
上記の表どおりに MAJOR/MINOR を使い分ける。

DriveManifest は自身が書かれた時点の SCHEMA_VERSION を記録し、
読み手 (studio) は MAJOR 一致を要求する。
"""

SCHEMA_VERSION = "0.3.0"


def major(version: str = SCHEMA_VERSION) -> int:
    """MAJOR 部を返す。互換性判定に使う。"""
    return int(version.split(".", 1)[0])
