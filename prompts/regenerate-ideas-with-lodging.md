# 改善案アイディア再生成プロンプト（宿泊データ込み）

Cowork（または通常のClaude.ai）に貼り付けて使う雛形。

---

## 使い方

1. このファイル全体をCoworkにペースト
2. `[[EVENT_KEY]]` を生成対象のイベントキーに置換
   - `sengoku-hanabi-2025` / `360-of-2025` / `shiki-aggregate`
3. 関連JSONファイルをCoworkにアップロード（または内容をコピペで貼り付け）
   - `data/events/lodging-annual.json`（必須・全イベント共通）
   - `data/events/sns-events-meta.json`（あれば）
   - 既存の `data/events/ideas-[[EVENT_KEY]].json`（差分更新したい場合）
4. Claudeに依頼 → 出力JSONを `data/events/ideas-[[EVENT_KEY]].json` に保存
5. github.dev でcommit & push → Netlifyが自動デプロイ

---

## プロンプト本文（ここからコピペ）

あなたは米沢観光推進機構（プラットヨネザワ）のデータアナリストです。
米沢で開催されるイベントの改善案を、複数データソースのエビデンスに基づいて生成してください。

**対象イベント**: `[[EVENT_KEY]]`

**入力データ**:
- `lodging-annual.json` — じゃらん宿泊データ（R6+R7・24ヶ月分の月次データ＋年度サマリ）
- `sns-events-meta.json`（あれば）— SNS分析メタ情報
- 既存の `ideas-[[EVENT_KEY]].json`（あれば差分更新の参考に）
- 必要に応じてCoworkで Web 検索やドキュメント参照

**必須要件**:

1. **宿泊観点を必ず含める**：
   - 出力JSON冒頭に `lodging_context` ブロックを置く
   - イベント開催月のR6/R7比較（取扱額・人泊数・単価）を必ず数値で示す
   - `insight` フィールドで「この月の宿泊動向の特徴」を1〜2文に要約
   - 改善アイディアの最低 50% で `evidence` に `source: "lodging"` を含む項目を1件以上含める
   - `lodging-annual.json` の月次データを根拠として活用（例：「10月R7人泊数6,022（前年比+20%）」のように具体的数値）

2. **アイディアは6カテゴリーで網羅**：
   - `shukyaku`（集客向上）
   - `manzoku`（満足度向上）
   - `pr`（PR・プロモ強化）
   - `shouhin`（商品開発）← ここに宿泊パッケージ案を入れやすい
   - `unei`（運営改善）
   - `data`（データ整備）

3. **各アイディアの構造**:
   ```json
   {
     "category": "shouhin",
     "category_label": "商品開発",
     "title": "アクション可能な短文（30字以内）",
     "evidence": [
       {"source": "lodging|sns|camera|agoop|analysis", "data": "数値や事実を具体的に"}
     ],
     "action": "誰が・いつまでに・何を・いくらで実行するか",
     "impact_text": "期待効果を数値で（人泊数・取扱額・客単価等）",
     "priority": "high|medium|low"
   }
   ```

4. **出力JSON全体の構造**:
   ```json
   {
     "event_id": "[[EVENT_KEY]]",
     "event_name": "イベント正式名称",
     "generated_at": "現在時刻のISO8601 (+09:00)",
     "data_sources_used": ["sns", "camera", "lodging", "agoop", "analysis"],
     "summary": "イベント全体の状況を3〜4文で",
     "lodging_context": {
       "event_period": "YYYY-MM (M/D-M/D)",
       "r7_month": {"torihiki_man": <数値>, "jinpaku": <数値>, "tanka_yen": <数値>},
       "r6_month": {"torihiki_man": <数値>, "jinpaku": <数値>, "tanka_yen": <数値>},
       "yoy_pct": {"torihiki": <数値>, "jinpaku": <数値>, "tanka": <数値>},
       "insight": "宿泊動向の特徴を1〜2文で"
     },
     "ideas": [
       /* 6〜8件、6カテゴリーを必ず1件以上カバー */
     ]
   }
   ```

5. **重要な禁則**:
   - ハルシネーション禁止：数値は `lodging-annual.json` 等の入力データに必ず存在するもののみ
   - 抽象論禁止：すべてのアクションに「誰が」「いつ」「いくら」を含める
   - エビデンス無しのアイディア禁止：`evidence` 配列は最低2件

6. **米沢の文脈**:
   - 米沢観光推進機構（DMO）／プラットヨネザワ（運営）／米沢市の役割分担を意識
   - 上杉謙信・鷹山公の文脈、米沢牛・米沢織、小野川温泉・白布温泉の地理関係
   - 山形新幹線「つばさ」E8系（2024年運行開始）、東北中央道（福島〜米沢）
   - 首都圏（特に東京都）からの誘客が共通課題

---

## 出力例

既存の `data/events/ideas-sengoku-hanabi-2025.json` を参考にしてください（特に最後の「戦国花火 翌朝の温泉延泊プラン」が宿泊観点ベースの典型例）。

---

## バージョン
- v1.0 (2026-05-12) — 初版（じゃらんR6+R7データ反映）
