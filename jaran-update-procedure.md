# じゃらん予約データ取り込み手順書

じゃらんエリアダッシュボードからエクスポートした「予約状況_日別データ」（宿泊 / 遊び体験）を、米沢観光ダッシュボード（`index.html`）に反映するための手順。

`jinryu-update-procedure.md`（人流データ取り込み手順）と同じ思想で `scripts/jaran-aggregate.py` を使う方式。CSV を1コマンドで集計 JSON 化し、`index.html` 側は JSON を読み込む（または出力された KPI 値をベタ書きで貼り替える）構成。

---

## 0. 前提

### 必要なもの

- じゃらんエリアダッシュボードからダウンロードしたCSV
  - 宿泊：「じゃらん予約状況_宿泊_日別データ」をCSVエクスポート
  - 遊び体験：「じゃらん予約状況_遊び体験_日別データ」をCSVエクスポート
- リポジトリ `koplat/yonezawa-dashboard` への push 権限
- Python 3（macOSには標準でプリインストール済）
- Node.js（`npm run serve` 用）

### 全体像（処理時間 目安：15〜30分／回）

```
1. スプシをCSVダウンロード → 2. data/raw/ に配置 →
3. jaran-aggregate.py 実行 → 4. index.html 編集 →
5. ローカル確認 → 6. commit & push
```

### スプレッドシートの列構成（参考）

両スプシは14列で、最後の3列だけ kind 依存。

| 列 | 宿泊 | 遊び体験 |
|---|---|---|
| 9列目 | `宿泊人泊数` | `人数` |
| 10列目 | `人泊数_比較年実績` | `人数_比較年実績` |
| 11列目 | `人泊数_比較年予約` | `人数_比較年予約` |
| 12列目 | `宿泊人泊単価` | `単価` |

値の表記：

- 取扱額：`76万円` 形式（万円単位、precision は10000円）
- 人泊数 / 人数：`82`（整数）。前年比較列は `63 (130.2%)` 形式
- 単価：`9,321` または `9321`（カンマ込み可）
- `※`：データ件数が少なく非表示（マスク）
- 空文字：未集計または該当データなし
- 比較年実績 と 比較年予約：過去日では同一値（同年予約と実績が一致）

---

## 1. リポジトリの場所を確認

ローカルのclone先：

```
~/Documents/yonezawa-dashboard
```

※ iCloud Drive管理下にある場合、Finderで「ダウンロード」マークがついていたら**同期完了を待つ**こと。

---

## 2. スプシをCSVエクスポート

各スプシを開き、「ファイル → ダウンロード → カンマ区切り形式 (.csv)」。

- 宿泊：[じゃらん予約状況_宿泊_日別データ](https://docs.google.com/spreadsheets/d/1VLAtLm7QYVUo6sADFOjFbZ26ul5J2FBBJVe4Djewfnw/edit)
- 遊び体験：[じゃらん予約状況_遊び体験_日別データ](https://docs.google.com/spreadsheets/d/15dtiVd3igarQ2-BXY9s_-R90OqAISAlzLntig2aPiUY/edit)

ファイル名の命名規則：

```
data/raw/lodging/lodging-{event-id|period-id}.csv
data/raw/experience/experience-{event-id|period-id}.csv
```

例：

```
data/raw/lodging/lodging-uesugi-matsuri-2025.csv
data/raw/lodging/lodging-2026-04.csv               # 月次
data/raw/lodging/lodging-fy2025.csv                # 年度通期
data/raw/experience/experience-uesugi-matsuri-2025.csv
```

ターミナルでの配置例：

```bash
mkdir -p ~/Documents/yonezawa-dashboard/data/raw/{lodging,experience}
mv ~/Downloads/じゃらん予約状況_宿泊_日別データ\ -\ Sheet1.csv \
   ~/Documents/yonezawa-dashboard/data/raw/lodging/lodging-fy2025.csv
mv ~/Downloads/じゃらん予約状況_遊び体験_日別データ\ -\ Sheet1.csv \
   ~/Documents/yonezawa-dashboard/data/raw/experience/experience-fy2025.csv
```

---

## 3. 集計スクリプトを実行

`scripts/jaran-aggregate.py` を使う。

### 3-1. イベント単位で集計（推奨：6イベントごと）

`data/events/sns-events-meta.json` に登録された `date_start` / `date_end` を参照してイベント期間を抽出する。

```bash
cd ~/Documents/yonezawa-dashboard

# 宿泊：米沢上杉まつり2025期間
python3 scripts/jaran-aggregate.py \
    --input data/raw/lodging/lodging-uesugi-matsuri-2025.csv \
    --kind lodging \
    --event uesugi-matsuri-2025

# 遊び体験：戦国花火2025期間
python3 scripts/jaran-aggregate.py \
    --input data/raw/experience/experience-sengoku-hanabi-2025.csv \
    --kind experience \
    --event sengoku-hanabi-2025
```

出力：

- 標準出力にKPIサマリー（取扱額・人泊数／人数・前年比・比較可能日のみの前年比）
- `data/events/lodging-{event-id}.json` ／ `data/events/experience-{event-id}.json`

### 3-2. 通期・月次で集計

```bash
# 月次（2026年4月）
python3 scripts/jaran-aggregate.py \
    --input data/raw/lodging/lodging-2026-04.csv \
    --kind lodging \
    --period 2026-04 \
    --date-start 2026-04-01 --date-end 2026-04-30

# 年度通期（令和7年度）
python3 scripts/jaran-aggregate.py \
    --input data/raw/lodging/lodging-fy2025.csv \
    --kind lodging \
    --period fy2025 \
    --date-start 2025-04-01 --date-end 2026-03-31
```

### 3-3. オプション

| オプション | 用途 |
|---|---|
| `--input PATH` | 入力CSV（必須） |
| `--kind lodging\|experience` | データ種別（必須） |
| `--event EVENT_ID` | sns-events-meta.json の date_start/end を使う |
| `--period PERIOD_ID` | 出力ファイル名 suffix（--date-start/end と併用） |
| `--date-start YYYY-MM-DD` | 集計開始日 |
| `--date-end YYYY-MM-DD` | 集計終了日 |
| `--events-meta PATH` | イベントメタJSONパス指定（既定 `data/events/sns-events-meta.json`） |
| `--output PATH` | 出力JSONパス上書き |
| `--print-daily` | stdout に日別データ先頭10件を表示 |

### 3-4. 出力JSONの構造

```json
{
  "kind": "lodging",
  "period_id": "uesugi-matsuri-2025",
  "period_label": "米沢上杉まつり",
  "period": {"start": "2025-04-29", "end": "2025-05-03"},
  "daily": [
    {"date": "2025-04-29", "weekday": "火", "amount_yen": 4000000, "persons": 294, ...}
  ],
  "kpi": {
    "total_amount_yen": 13580000,
    "total_persons": 1135,
    "unit_label": "人泊",
    "average_unit_price_yen": 11965,
    "counted_days": 5,
    "masked_days": 0
  },
  "yoy": {
    "amount_yoy_ratio": 0.898,
    "persons_yoy_ratio": 0.924,
    ...
  },
  "comparable_yoy": {
    "note": "当年・前年ともに値がある日だけで合算した前年比（マスク日除外）",
    "comparable_days": 5,
    "amount_yoy_ratio": 0.898,
    "persons_yoy_ratio": 0.924
  },
  "weekday_summary": [
    {"weekday": "月", "count_days": 1, "avg_persons": 294.0, ...}
  ],
  "source": {...}
}
```

---

## 4. index.html を編集

このCSVが供給できるのは「日次の取扱額・人泊数・単価・前年比較」までで、**発地別・年代別・リードタイム・属性データは含まれない**。マニュアル §8.1 に挙げられた `chartLodgeOrigin` / `chartLodgeLead` / `chartLodgeAge` は別データソース（じゃらんエリアダッシュボードの別CSV）が必要。

### 4-1. このスクリプトで埋められるチャート・KPI

| 反映先 | データ源 |
|---|---|
| KPI「期間累計取扱額」「累計宿泊人泊数」「平均単価」「前年比」 | `kpi` / `yoy` / `comparable_yoy` |
| 日別取扱額・人泊数のタイムライン折れ線 | `daily[].amount_yen`, `daily[].persons` |
| 前年同期比のオーバーレイ | `daily[].amount_prev_actual_yen` |
| 曜日別の平均人泊数（棒グラフ） | `weekday_summary` |
| データ品質バッジ（マスク日数） | `kpi.masked_days` |

### 4-2. JSON読み込み版（推奨・新規実装）

`index.html` の該当タブで `fetch()` から JSON を読み込む。SNS反響タブのパターンに合わせるとよい。

```html
<script>
fetch('data/events/lodging-uesugi-matsuri-2025.json')
  .then(r => r.json())
  .then(data => {
    // KPIカード反映
    document.getElementById('kpiLodgeAmount').textContent =
      (data.kpi.total_amount_yen / 10000).toLocaleString() + '万円';
    document.getElementById('kpiLodgePersons').textContent =
      data.kpi.total_persons.toLocaleString() + '人泊';
    document.getElementById('kpiLodgeYoY').textContent =
      (data.comparable_yoy.persons_yoy_ratio * 100).toFixed(1) + '%';

    // 日別タイムライン
    new Chart(document.getElementById('chartLodgeDaily'), {
      type: 'line',
      data: {
        labels: data.daily.map(d => d.date),
        datasets: [
          { label: '今年（人泊）', data: data.daily.map(d => d.persons),
            borderColor: '#a01c1c', tension: 0.3 },
          { label: '前年実績（人泊）', data: data.daily.map(d => d.persons_prev_actual),
            borderColor: '#c9a96e', tension: 0.3, borderDash: [5,5] }
        ]
      }
    });
  });
</script>
```

### 4-3. ベタ書き版（暫定・人流データ手順と同じ）

スクリプト stdout の値を `index.html` の Chart() 内 `data:` 配列・KPI `<div class="kpi-value">` に直接ペースト。

```html
<!-- BEFORE -->
<div class="kpi-value">12,300<span class="kpi-unit">人泊</span></div>

<!-- AFTER -->
<div class="kpi-value">1,135<span class="kpi-unit">人泊</span></div>
```

```javascript
new Chart(document.getElementById('chartLodgeDaily'), {
  type: 'line',
  data: {
    labels: ['4/29','4/30','5/1','5/2','5/3'],
    datasets: [
      { label: '今年（人泊）', data: [294,202,203,168,268], ... },
      { label: '前年実績', data: [193,186,211,251,388], ... }
    ]
  }
});
```

### 4-4. データソース管理タブの切替

`index.html` 末尾のデータソース管理タブで、該当行を `pending` → `ready` に。

```html
<span class="status-pill pending">未投入</span>
↓
<span class="status-pill ready">投入済</span>
```

### 4-5. dummy-banner の除去

実データに置き換えたタブの `<div class="dummy-banner">…</div>` を削除。

---

## 5. ローカル確認

```bash
cd ~/Documents/yonezawa-dashboard
npm run serve
```

ブラウザで `http://localhost:8080` を開き、以下を確認：

- KPI値・グラフ・前年比が新データと一致
- グラフが描画されている（白くなっていない）
- ブラウザ Console（⌘+Option+I）に赤エラーが出ていない
- データソース管理タブで「投入済」になっている
- dummy-banner が消えている

確認後、ターミナルで `Ctrl + C` で http-server 停止。

---

## 6. commit & push

### 6-1. 状態確認

```bash
git status
```

### 6-2. ステージング

```bash
git add scripts/jaran-aggregate.py               # 初回のみ
git add data/raw/lodging/lodging-{event-id}.csv
git add data/raw/experience/experience-{event-id}.csv  # 遊び体験も入れた場合
git add data/events/lodging-{event-id}.json
git add data/events/experience-{event-id}.json         # 遊び体験も入れた場合
git add index.html
```

### 6-3. コミット

```bash
git commit -m "feat({event-id}): じゃらん予約データを実数値投入（期間累計 X,XXX人泊・前年比 XX.X%）"
```

例：

```bash
git commit -m "feat(uesugi-matsuri-2025): じゃらん予約データを実数値投入（1,135人泊・前年比 92.4%）"
```

### 6-4. push

```bash
git push origin main
```

### 6-5. 本番反映確認（push後1〜2分）

```
https://koplat.github.io/yonezawa-dashboard/
```

---

## 7. つまずきポイント

### CSVヘッダが認識されない

エラー：`CSVに必要な列がありません: {...}`

→ スプシをエクスポートし直す。ヘッダ行に `日付` `取扱額` `宿泊人泊数`（または `人数`）`宿泊人泊単価`（または `単価`）が必須。CSV1行目が空白行になっていないか確認。

### 前年比が現実離れした値になる

→ じゃらんの `※` マスク日が含まれていると、当年は値あり / 前年マスクの日が混じり比率が歪む。stdout の `[比較可日のみ: ...]` または JSON の `comparable_yoy.*_yoy_ratio` を使うこと。

### `--event` 指定でエラー

エラー：`event-id 'xxx' が data/events/sns-events-meta.json に未登録です`

→ Notion運用マニュアル §5 に従って `sns-events-meta.json` に当該 event-id を先に登録する。`date_start` / `date_end` が必須。

### 取扱額の万円端数が合わない

→ じゃらん「取扱額」は万円単位で四捨五入された表示値（precision 10000円）。日別の合計と期間集計値が ±数万円ずれるのは仕様。

### `iCloud` でCSVが見えない

→ Finderで該当ファイルに「⚠️」マークが出ていたら同期未完。マークが消えるのを待つ。

---

## 8. データ出典の標準クレジット

```
出典：じゃらんエリアダッシュボード（リクルート）
データ種別：宿泊 / 遊び体験
集計期間：{YYYY/MM/DD}〜{YYYY/MM/DD}
取得日：{YYYY/MM/DD}
```

---

## 9. 今後の発展余地

このスクリプトは「日別の取扱額・人泊数・前年比較」までしか集計しない。マニュアル §8.1 で挙げられている `chartLodgeOrigin`（発地別）・`chartLodgeLead`（リードタイム）・`chartLodgeAge`（年代別）を実データ化するには、じゃらんエリアダッシュボードの別CSV（発地別／リードタイム別／年代別）の取得と、専用パーサ（`scripts/jaran-segment-aggregate.py` 等）の新設が必要。今後タスク化することを推奨する。

---

## 付録：困ったときのコマンド集

```bash
# 直近のコミットを取り消す（push前のみ）
git reset --soft HEAD~1

# 直前のコミットメッセージを修正
git commit --amend -m "新しいメッセージ"

# 編集を全部破棄
git restore index.html data/events/lodging-*.json

# どのファイルをどう変更したか確認
git diff index.html | less

# スクリプト単体テスト
python3 scripts/jaran-aggregate.py \
    --input data/raw/lodging/lodging-fy2025.csv \
    --kind lodging \
    --period fy2025 \
    --date-start 2025-04-01 --date-end 2026-03-31 \
    --print-daily
```
