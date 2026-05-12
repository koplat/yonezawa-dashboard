# 米沢観光データダッシュボード

プラットヨネザワ／米沢観光推進機構（DMO登録第30119号）の主要イベント実績ダッシュボード。

## 構成

```
.
├── index.html                       # ダッシュボード本体（バニラHTML+Chart.js+Leaflet+wordcloud2）
├── data/
│   ├── events/                      # イベント別JSONデータ
│   │   ├── sns-events-meta.json     # SNS取得対象のメタデータ（ハッシュタグ・期間）
│   │   └── sns-{event-id}.json      # SNS反響集計（ingest後に生成）
│   └── raw/                         # 元データ（CSVなど・git管理）
├── scripts/
│   └── sns-process.ts               # SNS CSV → JSON 変換・感情分析・キーワード抽出
├── .claude/
│   └── commands/
│       └── sns-update.md            # Claude Code 用スラッシュコマンド
├── package.json
├── tsconfig.json
├── netlify.toml
└── README.md
```

## SNS反響データの更新（Claude Code連携）

完全無料・手動収集ゼロ。Claude Code を使って Yahoo!リアルタイム検索からX投稿を取得し、感情分析・JSON更新・git pushまで自動で行います。

### 初回セットアップ

```bash
# 1. Claude Code をインストール
# https://www.anthropic.com/claude-code

# 2. 本リポジトリをクローン
git clone <repo-url>
cd yonezawa-dashboard

# 3. 依存パッケージをインストール
npm install
```

### 運用：イベント終了後にSNS反響を更新

```bash
# 1. ターミナルで Claude Code を起動
cd /path/to/yonezawa-dashboard
claude

# 2. スラッシュコマンドを実行
> /sns-update sengoku-hanabi-2025
```

Claudeが以下を順番に自動実行します：

1. **Yahoo!リアルタイム検索でハッシュタグ検索**（`#よねざわ戦国花火大会` など）
2. 上位30投稿を抽出（投稿日・本文・いいね数・ハッシュタグ）
3. CSV保存：`data/raw/sns-sengoku-hanabi-2025.csv`
4. 解析実行：`npx tsx scripts/sns-process.ts --event sengoku-hanabi-2025`
5. JSON生成：`data/events/sns-sengoku-hanabi-2025.json`
6. git commit & push
7. Netlify自動再デプロイ → 数分後にダッシュボード反映

所要時間：1イベント約3〜5分。費用：Claude Codeサブスクリプションのみ（年¥36,000）。

### イベントID一覧

| event-id | イベント名 | 開催日 |
|---|---|---|
| `uesugi-matsuri-2025` | 米沢上杉まつり | 4/29-5/3 |
| `suijou-hanabi-2025` | 米沢納涼水上花火大会 | 8/8 |
| `360-of-2025` | 360°よねざわオープンファクトリー | 9/11-13 |
| `naseba-aki-2025` | なせばなる秋まつり | 9/27-28 |
| `sengoku-hanabi-2025` | よねざわ戦国花火大会 | 10/11 |
| `yukidouro-2026` | 上杉雪灯篭まつり | 2/14-15 |

### 手動でCSVを用意する場合

Claude Code を使わず、手動でCSVを作る運用も可能です：

```csv
date,platform,handle,text,likes,reposts,hashtags
2025-10-11,X,@example,戦国花火すごかった！,42,8,#よねざわ戦国花火大会|#米沢
```

CSVを `data/raw/sns-{event-id}.csv` に保存し、以下を実行：

```bash
npm run sns-process -- --event sengoku-hanabi-2025
git add . && git commit -m "chore: 戦国花火 SNS反響更新" && git push
```

## 公開先

### GitHub Pages（メイン・無料）

- **URL**: https://koplat.github.io/yonezawa-dashboard/
- `.github/workflows/pages.yml` が main への push 毎に自動デプロイ
- 初回有効化：リポジトリ Settings → Pages → Source を **"GitHub Actions"** に設定

### Netlify（代替・必要に応じて）

- `netlify.toml` の設定でセキュリティヘッダー等が効く
- 過去の URL: `https://sparkly-kashata-f63e66.netlify.app/`
- Netlify Drop に zip ドラッグ&ドロップでも公開可能

## ライセンス

社内利用限定（米沢観光推進機構）。データソースの利用規約に従ってください。

## 改善案の自動生成（横断データ統合）

各イベントの「改善点・提案アイディア」セクションは、人流・カメラ・宿泊・SNS反響の各データを横断分析した結果を JSON ファイルとして保存しています。Claude Code の `/ideas-generate` コマンドで再生成・更新可能です。

### 使い方

```bash
# Claude Code を起動
claude

# 改善案を生成（戦国花火の例）
> /ideas-generate sengoku-hanabi-2025
```

Claude が以下を自動実行します：
1. `data/events/sns-{event-id}.json` 等の利用可能なデータを横断的に読み込み
2. 各データソースのKPI・トレンド・ネガポイントを抽出
3. 6カテゴリ（集客/満足度/運営/PR/商品開発/データ整備）で改善案を5〜10案生成
4. 各案に複数データソース横断の根拠を付与
5. `data/events/ideas-{event-id}.json` として保存
6. git commit & push → Netlify自動デプロイ

### データ構造

`data/events/ideas-{event-id}.json` の例：

```json
{
  "event_id": "sengoku-hanabi-2025",
  "event_name": "よねざわ戦国花火大会",
  "generated_at": "2026-05-09T10:00:00+09:00",
  "data_sources_used": ["sns", "camera", "lodging"],
  "summary": "横断分析で見えた論点を1-2文で",
  "ideas": [
    {
      "category": "shukyaku",
      "category_label": "集客向上",
      "title": "首都圏向け早期チケット販売の拡大",
      "evidence": [
        {"source": "sns", "data": "「早期完売を惜しむ声」コメント多数"},
        {"source": "lodging", "data": "GW宿泊客の発地TOP=東京都17%"},
        {"source": "camera", "data": "戦国花火10/11の道の駅米沢通過1,718台"}
      ],
      "action": "有料観覧席を1.5倍枠拡張、首都圏向け新幹線セットパッケージを8月公開",
      "impact_text": "観覧席取扱額+30%、首都圏来訪者倍増",
      "priority": "high"
    }
  ]
}
```

### イベントID（改善案生成対象）

| event-id | 統合先タブ |
|---|---|
| `sengoku-hanabi-2025` | 戦国花火大会タブ |
| `360-of-2025` | 360°オープンファクトリータブ |
| `shiki-aggregate` | 四季のまつりタブ（春・夏・秋・冬の4イベント横断） |

### ダッシュボードでの表示

各イベントタブを開くと、`data/events/ideas-{event-id}.json` が自動的に fetch されて改善案セクションに反映されます。最終更新日時・統合データソース・提案数も表示。

ファイルが存在しない場合は「Claude Code で /ideas-generate を実行してください」というプレースホルダーが表示されます。
