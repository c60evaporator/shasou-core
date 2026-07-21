# CLAUDE.md — shasou-core
このファイルはClaude Code が shasou-core を実装・拡張する際の指針。設計判断の背景と「なぜそうなっているか」を集約する。**コードを書く前に必ず読むこと。**

## 0. shasou-core とは
shasou (車窓, *shasō*) エコシステムの共有スキーマ・規約パッケージ。実車/CARLAで収集したEnd-to-end自動運転向けデータをnuScenes形式へ変換する一連のツール群が、この1パッケージの契約を共有する。まずはshasouエコシステムの概要について解説する
### shasou eco system概要
shasouエコシステムは、以下のフローでEnd-to-end自動運転向けのデータ収集・キュレーションを実施

```mermaid
flowchart LR
    A["車載収録<br/><span style='font-size:16px'>ROS 2 / MCAP</span>"]
    B["生データ保管<br/><span style='font-size:16px'>bag・校正・タグ</span>"]
    C["nuScenes互換データ変換<br/><span style='font-size:16px'>Raw層への取り込み</span>"]
    D["Scene切り取り<br/><span style='font-size:16px'>Scene境界作成</span>"]
    E["nuScenes形式出力<br/><span style='font-size:16px'>nuScenes JSON出力</span>"]
    A --> B --> C --> D --> E
```

shasouエコシステムは、以下3リポジトリから構成される
- **shasou-recorder**: Jetson等で動作させ、車載収録を実施するツールキット (ROS 2 / MCAP)。想定している概要は`docs/recorder_summary.md`も参照
- **shasou-studio**: recorderで取得したデータをインポートして保管し、nuScenes互換データ変換、Scene切り取り、nuScenes形式出力等を実施するためのWebアプリ。データキュレーションのための分析機能も含む
- **shasou-core** (本リポジトリ): 上記 2 つが共有するmanifestスキーマ・MCAPトピック規約・trajectory成果物形式をPydantic + JSON Schemaで定義

#### データの階層構造
記録されるデータは以下の階層構造を持つ

```mermaid
erDiagram
    platform ||--o{ drive : ""
    platform ||--o{ calibration : ""
    calibration ||--|{ calibration_sensor_entry : "含む"

    platform {
        string platform_id
        string sensor_rig
        string vehicle_type
    }
    drive {
        string drive_id
        string calib_id
        string status
        string archive_status
    }
    calibration {
        string calib_id
        date captured_at
    }
    calibration_sensor_entry {
        string channel
        json intrinsics
        json extrinsics
    }
```

- platform: 「学習データとして一体利用できる」ことを念頭に、センサ構成（sensor_rig）・車種（vehicle_type）が一致するデータをグルーピングしたもの。shasou-studioで定義を作成・管理し。recorderは同期時に取得（studio非依存のローカル定義でも動作可）
- drive: 1走行ごとに取得され、IDとしてdrive_idが割り当てられる。1つのdriveがnuScenes形式変換後のlogと1対1で対応。shasou-recorderが走行ごとに自動作成する
- calibration: キャリブレーション1回ごとに作成される（複数センサを含む）。1回のcalibrationはnuScenes形式変換時に複数センサ分のcalibrated_sensorレコードに展開される。shasou-recorderがキャリブレーションごとに自動作成する

#### データ収集のワークフロー
データ収集は以下の流れで実施
1. 設定のrecorderへの共有 ：shasou-studioで作成したplatform定義等の設定を、shasou-recorder側にダウンロード
2. 車上Jetson＋SSD（NVMe）で収録 ：shasou-recorderが実施
3. NAS：shasou-studioの直近数ヶ月程度のデータのストレージとして使用。書き込みはshasou-recorderが実施
4. S3：shasou-studioのアーカイブデータのストレージとして使用

各レコード（データの階層構造におけるdrive）はワークフローのどこにあるかをメタデータの`status`および`archive_status`で保持する。
- `status`は以下の状態から選ぶ
    - `recorded`：収録完了（車上SSDに存在）
    - `transferred`：NASへコピー完了（まだ検証前）
    - `verified`：チェックサム照合が通った（NAS上で健全性確認済み）
    - `imported`：shasou-studioがRaw層に取り込んだ
- `archive_status`は以下の状態から選ぶ
    - `none`：NASのみ
    - `archived`：S3標準
    - `glacier`：Glacier Deep Archive退避

## Directory Structure
shasou-coreは以下のディレクトリ構造を持つ。各ファイルの詳細は「3. ファイル別ガイド」で後述

```
shasou-core/
├── pyproject.toml              # 依存: pydantic v2のみ。extras: [io] pyarrow
├── README.md                   # スキーマ定義リポジトリに一般的に必要な内容を記述
├── CONTRIBUTING.md             # 「フレームワーク依存禁止」の規律を明文化
├── src/shasou_core/
│   ├── __init__.py
│   ├── version.py
│   ├── constants.py
│   ├── frames.py
│   ├── schemas/
│   │   ├── common.py
│   │   ├── platform.py
│   │   ├── manifest.py
│   │   ├── calibration.py
│   │   ├── topics.py
│   │   ├── events.py
│   │   ├── health.py
│   │   └── trajectory.py
│   ├── validation.py
│   └── io/                     # extra [io]
│       └── trajectory_io.py
├── jsonschema/v1/
├── scripts/export_jsonschema.py
└── tests/
    ├── test_*.py               # スキーマ単体 + 往復一致テスト
    └── fixtures/               # ★CARLAブリッジが実際に出力したmanifest等を実例フィクスチャとして格納
```

## 1. 絶対に守る規律

### 1.1 依存の規律 (最重要)
**ランタイム依存は pydantic のみ。** FastAPI / SQLAlchemy / ROS / numpy 等への
依存を `dependencies` に追加してはならない。理由: recorder は Jetson 上で動き、
Web アプリ都合の依存が混入すると車載側のビルドが汚れる。
- I/O 系 (pyarrow 等) は `[io]` のような optional extra に隔離する
- ROS 型はすべて**文字列**で表現する (`"sensor_msgs/msg/Image"`)。ROS への実依存は
  recorder の責務

### 1.2 スキーマ変更は SCHEMA_VERSION を伴う
`version.py` の `SCHEMA_VERSION` はデータ契約の SemVer。constants.py / manifest /
trajectory / topics 規約を変えたら上げる。manifest は書き込み時の版を記録し、
読み手は MAJOR 一致を要求する (`DriveManifest.is_schema_compatible`)。

### 1.3 生成物はコミットするが手で書かない
JSON Schema (`jsonschema/v1/`) は `model_json_schema()` からの生成物。CI で
「生成し直して差分ゼロ」を検証する。手編集しない。

---

## 2. 揺るがない設計思想 (エコシステム全体の憲法)

これらは過去の長い議論で確定した原則。実装判断で迷ったらここに立ち返る。

### 2.1 「正はソースに近い側」/ 非破壊・再生成可能
一次データ (MCAP) は不変。派生物 (nuScenes 出力、trajectory、events.jsonl) は
いつでも再生成できる。生値を焼き込まず、加工は下流の責務にする。
- 例: RADAR は生の相対動径速度のみ記録。自車運動補償 (vx_comp 相当) はエクスポータ
- 例: events.jsonl は bag からの派生物。正は bag 側
- 例: LiDAR は無補正のセンサフレームで記録。deskew は下流

### 2.2 token は切り出し前に確定し、以降不変
sample 等の token は Raw 層で採番し、Scene 切り出しが変わっても変えない。これに
より sample_annotation / instance 資産が切り出し変更に耐える。導出 token は
`derived_token()` (uuid5) で決定的に生成し、再エクスポートで安定させる。

### 2.3 内部表現は正規化、出力表現は互換優先
内部は正規化して持ち、nuScenes 出力時に互換のため複製・並び替えする。
- ego_pose は内部で正規化 (同時トリガならスイープ 1 ポーズ)、出力で sample_data
  ごとに複製 (nuScenes は ego_pose:sample_data = 1:1 を仮定)
- quaternion は内部 ROS 順 (xyzw)、nuScenes 出力で (wxyz) へ並び替え
- size は内部でフルサイズ+軸明示、nuScenes 出力で w,l,h 順へ

### 2.4 右手系のみ
shasou の世界に左手系 (CARLA/Unreal) は存在しない。CARLA ブリッジの境界で一度だけ
右手系へ変換し、以降は右手系。位置 `(x,-y,z)`、RPY `(roll,-pitch,-yaw)`、
舵角は左転舵正。変換は 1 モジュールに集約し散在させない。

### 2.5 チャネル集合の正は platform 定義
core は台数構成を固定しない。core が持つのは**命名規約** (`CAM_`/`LIDAR_`/`RADAR_`
プレフィックス + 大文字英数字)。実際のチャネル集合は platform.sensor_rig が正。
`NUSCENES_*_CHANNELS` は参考デフォルトであって上限ではない (6 台に限定しない)。

### 2.6 座標フレーム規約
- `base_link` = 後軸中心を路面高さへ投影した点 (nuScenes ego と同一)。空車時の
  静的高さで車体に剛結 (サス追従しない)
- センサフレーム = チャネル名小文字。カメラは `_optical` を追加 (Z前/X右/Y下)
- 画像トピックの frame_id は光学フレーム
- 動的 tf (map→base_link) は bag に記録しない。ego pose はトピック/trajectory で表現

---

## 3. ファイル別ガイド

### 実装済み (人間レビュー済み、勝手に変えない)
| ファイル | 役割 | 注意 |
|---|---|---|
| `version.py` | SCHEMA_VERSION と互換判定 | |
| `constants.py` | 単位規約・チャネル命名規約・時刻換算 | 「憲法」。変更は要 SCHEMA_VERSION |
| `frames.py` | tf tree・フレーム命名・静的 tf 期待値 | チャネル集合は引数で受ける (固定リスト持たない) |
| `schemas/common.py` | Token/時刻/Vector3/Quaternion/enum 群 | `EgoPoseBackend` はここが定義元 (共有語彙) |
| `schemas/topics.py` | MCAP トピック契約をデータとして定義 | RADAR=velocity_radial のみ必須。Depth は gt 配下 |
| `schemas/manifest.py` | DriveManifest | チャネルは命名規約のみ検証 (実在検証は validation) |
| `schemas/trajectory.py` | 軌跡成果物スキーマ | 選択肢 B: 1 drive 1 対多 backend |
| `schemas/platform.py` | Platform/ChannelSpec/CameraConfig/VehicleParams | 構成の**宣言** (公称値・型参照)。実測値は calibration 側 |
| `schemas/calibration.py` | CalibrationSet/SensorCalibEntry/CameraIntrinsics/SensorExtrinsics | キャリブ 1 回ごとの**実測値**。token は derived_token で決定的生成 |
| `schemas/events.py` | EventTag (events.jsonl 1 行 = ROS EventTag ペイロード) | type=閉じた enum / source=str (規約強制) / label=自由。timestamp のみ strict |
| `schemas/health.py` | TopicStat/TopicStats/DiskStats (topic_stats.json) | 計測値の器。良否判定は持たない (閾値は呼び出し側) |
| `io/trajectory_io.py` | Parquet 読み書き (extra) | pyarrow 依存はここだけ |
| `validation.py` | 横断検証 (manifest×platform×calib×topics) | Issue リストを返す (例外投げない) |
| `scripts/export_jsonschema.py` | 全スキーマの JSON Schema 生成 / `--check` | 出力は決定的 (sort_keys)。生成物は手編集禁止 |
| `scripts/check_dependencies.py` | 依存規律の番人 (§1.1) | io を除く全モジュールを pyarrow 抜きで import |
| `jsonschema/v1/*.json` | 上記の生成物 (コミット対象) | 手で書かない。CI が差分ゼロを検証 |
| `.github/workflows/ci.yml` | pytest + JSON Schema 差分ゼロ + 依存規律 | Python 3.10 / 3.13 マトリクス |

### 残タスク
| 箇所 | やること |
|---|---|
| `validation.py` の `TODO(next)` | `ChannelSpec.nominal_mount` (設計搭載位置) と `SensorExtrinsics` (実測) の乖離検証。許容閾値 (並進 [m] / 回転 [rad]) の設計が必要 |

---

## 4. 実装済みタスクで確定した設計判断

§4 の CLI 実装タスクは全て完了済み。以降の変更で前提を崩さないよう、そのとき
確定した判断を記録する (背景の議論は各ファイルの docstring にもある)。

### 4.1 platform.py / 4.2 calibration.py: 宣言 vs 実測の切り分け
`ChannelSpec` は**構成上の宣言** (公称解像度・FOV・期待する内部パラメータ
モデルの型参照・設計搭載位置 `nominal_mount`) を持ち、係数値は持たない。
`CalibrationSet` の entry は**キャリブ 1 回ごとの実測値** (`CameraIntrinsics`
の実測係数・`SensorExtrinsics` の実測搭載位置)。両者に現れる解像度・搭載位置は
重複ではなく公称/実測のペアで、照合は validation.py の責務。
歪みモデル語彙 `CameraIntrinsicsModel` は platform.py が定義元で calibration.py
が import して共有する (照合が enum 比較で済む)。
calibrated_sensor token は `derived_token(calib_id, channel)` で決定的生成 (§2.2)。
`VehicleParams` は Platform にネストされる区画で、車種の識別は
`Platform.vehicle_type` が唯一の正 (二重管理しない)。

### 4.3 events.py: 閉じた軸と開いた軸を分ける
`type` は閉じた enum (粗い分類軸。下流が網羅的に分岐するため固定語彙。追加は
SCHEMA_VERSION 更新を伴う)、`label` は自由記述 (具体性はここが担う)、`source`
は **str 型**で既知値のみ `EventSource` に置き、命名規約 `^[a-z][a-z0-9_]*$` を
validator で強制する (OSS 利用者が core を変更せず独自デバイスを足せる)。
`timestamp` のみ `strict=True`。素の `TimestampNs` では整数値 float
(`1752641234.0`) が黙って int に強制変換され、秒を ns 欄に入れる事故が通るため。

### 4.4 health.py: 計測値の器に徹する
`TopicStats` は良否判定 (`is_healthy()` 等) を持たない。閾値は platform や運用で
変わり、core に置くと閾値変更が SCHEMA_VERSION 更新を伴うため。判定は
呼び出し側 (recorder のヘルスモニタ / studio の取り込みフィルタ) の責務。

### 4.5 export_jsonschema.py: 決定的出力
`sort_keys=True` / `indent=2` / `ensure_ascii=False` / 末尾改行 1 つ。
`model_json_schema()` の出力に手を加えない (`$id` の後付けもしない)。
出力先の `v1` は**定数**で、SemVer の MAJOR とは連動させない (0.x = 初期開発中と
契約の世代番号は別概念)。運用規則: 0.x の間は v1、MAJOR≥2 で v2 を切る。

### 4.6 validation.py: 契約との突き合わせと重大度の非対称
sensor_config に現れないトピック (gt/vehicle/clock) は、名前空間がデプロイ依存
なので**末尾セグメントの後方一致**で判定する (期待末尾は
`resolve_topic_name("", channel, contract)` から得る)。per_channel 契約は
sensor_config を contract.modality で絞って展開し、gt_depth はカメラチャネルに
展開する。重大度は「欠けるとドライブが使えないもの」を ERROR、「構成・運用で
変わりうるもの」を WARNING とし、Issue code に非対称を反映する
(`gt_topic_absent` / `gt_depth_topic_absent`、`vehicle_topic_absent` /
`vehicle_aux_topic_absent` 等)。

### 4.7 テスト方針
新規スキーマごとに単体検証 + JSON/YAML 往復一致。`ShasouModel` は
`extra="forbid"` なので未知フィールド拒否もテストする。生成物は
「コードから生成し直して一致するか」をテストで固定する (§1.3)。

---

## 5. トピック規約リファレンス (topics.py の要約)

実装の正は topics.py。実車移行時も同じ契約 (source 固有アダプタが吸収)。

### 共通センサ (実車・CARLA 両方)
- カメラ: `<ns>/cam_<pos>/image_raw/compressed` (CompressedImage/jpeg) +
  `camera_info`。frame_id=光学フレーム。image_transport 規約で末尾 `/compressed`
- LiDAR: `<ns>/<ch>/points` (PointCloud2, x/y/z/intensity/ring)。センサフレーム・無補正
- RADAR: 同上。必須 x/y/z/velocity_radial (接近負)。rcs/dynprop は optional
- IMU: orientation 無効 (covariance[0]=-1)。生センサ扱い
- GNSS: NavSatFix

### 車両状態 (共通、CAN 相当)
- `vehicle/drive_state`: AckermannDriveStamped。speed=m/s(後退負), steering_angle=
  rad(左正・前輪実舵角)
- `vehicle/pedals`: JointState。name=`("throttle_pedal","brake_pedal")` 固定、
  position=[0,1]
- `vehicle/reverse`, `vehicle/handbrake`: Bool

### CARLA 特権情報 (Ground Truth、gt 名前空間)
- `gt/ego_odom`: Odometry。pose=map, twist=base_link。trajectory の源泉
- `gt/objects`: 全アクター 3D BBox+actor_id+クラス。map 座標。実体は shasou_msgs
- `gt/agent_plan`: Path (PDM-Lite 計画軌跡)
- `gt/depth_<pos>/image`: 32FC1 メートル深度。RGB と光学フレーム共有。**実車に無い**
- `/clock`: sim 時刻

### 実車限定 (CLI で REAL_ONLY として追加想定)
GNSS 生観測 (PPK 用)、生 CAN (`can_msgs/Frame`)。DBC 再デコード可能に生も録る。

### CARLA 固有の変換注意
- LiDAR `rotation_frequency` = sim レート (20) に合わせる (1 tick 1 周)
- BBox extent は半寸法 → 2 倍。size 並びは w,l,h
- 全センサ 20Hz 同時トリガ = 同時トリガパターン。ego_pose は sample_data ごとに複製
- キーフレーム = 10 tick ごと (2Hz)

---

## 6. データ階層とワークフロー (recorder 側、参考)

```
platform (sensor_rig + vehicle_type 一致で「学習データとして一体利用可」)
 ├─ drive (1 走行 = nuScenes log と 1:1)
 └─ calibration (1 回 = 複数 calibrated_sensor に展開, 1:N)
```

manifest の `status`: recorded→transferred→verified→imported。recorder は
verified まで書き、imported は studio が catalog へ書き戻す。S3 退避は status と
別軸の `archive_status` (none/archived/glacier)。

platform 定義は studio が編集元、recorder は同期取得 (PlatformProvider 抽象:
LocalFileProvider でスタンドアロンも可)。使用した定義の版を manifest に刻む。

---

## 7. 開発コマンド

```bash
pip install -e ".[dev,io]"     # 開発セットアップ
pytest                          # 全テスト (現在 177 件。io 無しだと 1 件 skip)
python scripts/export_jsonschema.py           # JSON Schema 再生成
python scripts/export_jsonschema.py --check   # 生成物がコードと一致するか
```

依存規律の検証は io extra を**入れない**環境で行う (pyarrow があると空振りする):

```bash
pip install -e ".[dev]"
python scripts/check_dependencies.py
```

変更を入れたら: テストが通ること + JSON Schema 差分ゼロ + §1 の依存規律を確認。
CI (`.github/workflows/ci.yml`) がこの 3 点を push / PR で自動検証する。
