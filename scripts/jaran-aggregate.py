#!/usr/bin/env python3
"""
じゃらん予約日別データ集計スクリプト（宿泊 / 遊び体験 共通）

じゃらんエリアダッシュボードからダウンロードした「予約状況_日別データ」CSV を
集計し、ダッシュボード反映用の JSON を生成する。
人流データの scripts/jinryu-aggregate.py と同じ思想で設計してある。

Usage:
    # イベント単位（米沢上杉まつり2025の期間で抽出）
    python3 scripts/jaran-aggregate.py \\
        --input data/raw/lodging/lodging-uesugi-matsuri-2025.csv \\
        --kind lodging \\
        --event uesugi-matsuri-2025

    # 通期・月次（日付範囲を直接指定）
    python3 scripts/jaran-aggregate.py \\
        --input data/raw/lodging/lodging-2026-04.csv \\
        --kind lodging \\
        --period 2026-04 \\
        --date-start 2026-04-01 --date-end 2026-04-30

    # 範囲指定なし（CSV全期間を1まとめ）
    python3 scripts/jaran-aggregate.py \\
        --input data/raw/lodging/lodging-fy2025.csv \\
        --kind lodging --period fy2025

    # 遊び体験も同じインターフェース
    python3 scripts/jaran-aggregate.py \\
        --input data/raw/experience/experience-uesugi-matsuri-2025.csv \\
        --kind experience --event uesugi-matsuri-2025

入力CSV: じゃらんエリアダッシュボード「予約状況_日別データ」をCSVエクスポート
出力JSON: data/events/{kind}-{event-or-period}.json
"""
from __future__ import annotations

import argparse
import csv
import json
import re
import sys
from datetime import date, datetime
from pathlib import Path
from typing import Optional

# ---- 定数 --------------------------------------------------------------------
KIND_LODGING = "lodging"
KIND_EXPERIENCE = "experience"

# kind毎の列名対応（じゃらんCSVのヘッダ）
COL_PERSONS = {
    KIND_LODGING: "宿泊人泊数",
    KIND_EXPERIENCE: "人数",
}
COL_PERSONS_PREV_ACTUAL = {
    KIND_LODGING: "人泊数_比較年実績",
    KIND_EXPERIENCE: "人数_比較年実績",
}
COL_PERSONS_PREV_RESERVED = {
    KIND_LODGING: "人泊数_比較年予約",
    KIND_EXPERIENCE: "人数_比較年予約",
}
COL_UNIT_PRICE = {
    KIND_LODGING: "宿泊人泊単価",
    KIND_EXPERIENCE: "単価",
}
COL_UNIT_PRICE_PREV_ACTUAL = {
    KIND_LODGING: "単価_比較年実績",
    KIND_EXPERIENCE: "単価_比較年実績",
}

UNIT_LABEL = {
    KIND_LODGING: "人泊",
    KIND_EXPERIENCE: "人",
}


# ---- パーサ ------------------------------------------------------------------

def parse_amount(s: Optional[str]) -> Optional[int]:
    """ '76万円' -> 760000, '※' -> None, '' -> None, '65万円 (117.0%)' -> 650000 """
    if s is None:
        return None
    s = s.strip()
    if s == "" or s == "※":
        return None
    m = re.match(r"^([\-\d,]+)万円", s)
    if not m:
        return None
    n = int(m.group(1).replace(",", ""))
    return n * 10000


def parse_count(s: Optional[str]) -> Optional[int]:
    """ '82' -> 82, '63 (130.2%)' -> 63, '※' -> None """
    if s is None:
        return None
    s = s.strip()
    if s == "" or s == "※":
        return None
    m = re.match(r"^([\-\d,]+)", s)
    if not m:
        return None
    return int(m.group(1).replace(",", ""))


def parse_ratio(s: Optional[str]) -> Optional[float]:
    """ '65万円 (117.0%)' -> 1.17, '※' -> None, '' -> None """
    if s is None:
        return None
    s = s.strip()
    if s == "" or s == "※":
        return None
    m = re.search(r"\(([\d\.]+)%\)", s)
    if not m:
        return None
    return float(m.group(1)) / 100.0


def parse_date(s: str) -> Optional[date]:
    if not s:
        return None
    try:
        return datetime.strptime(s.strip(), "%Y-%m-%d").date()
    except ValueError:
        return None


def safe_div(a: Optional[float], b: Optional[float]) -> Optional[float]:
    if a is None or b is None or b == 0:
        return None
    return a / b


def fmt_ratio(r: Optional[float]) -> str:
    if r is None:
        return "—"
    return f"{r * 100:.1f}%"


# ---- イベントメタ ------------------------------------------------------------

def load_event_meta(events_meta_path: Path, event_id: str) -> dict:
    if not events_meta_path.exists():
        raise FileNotFoundError(
            f"イベントメタファイルが見つかりません: {events_meta_path}\n"
            "  --events-meta オプションでパスを指定するか、"
            "data/events/sns-events-meta.json を配置してください。"
        )
    with open(events_meta_path, encoding="utf-8") as f:
        data = json.load(f)
    if event_id not in data:
        raise KeyError(
            f"event-id '{event_id}' が {events_meta_path} に未登録です。\n"
            "  既存のキー一覧: " + ", ".join(sorted(data.keys()))
        )
    return data[event_id]


# ---- 集計 --------------------------------------------------------------------

def aggregate(rows: list[dict], kind: str) -> dict:
    col_persons = COL_PERSONS[kind]
    col_persons_prev_actual = COL_PERSONS_PREV_ACTUAL[kind]
    col_persons_prev_reserved = COL_PERSONS_PREV_RESERVED[kind]
    col_unit_price = COL_UNIT_PRICE[kind]

    daily: list[dict] = []
    weekday_persons: dict[str, list[int]] = {}
    masked_days = 0
    counted_days = 0
    total_amount = 0
    total_persons = 0
    total_amount_prev_actual = 0
    total_persons_prev_actual = 0
    total_amount_prev_reserved = 0
    total_persons_prev_reserved = 0
    # comparable: 当年・前年ともに値がある日だけを合算（前年比の歪み防止）
    cmp_total_amount = 0
    cmp_total_persons = 0
    cmp_total_amount_prev = 0
    cmp_total_persons_prev = 0
    cmp_days = 0

    for r in rows:
        d = parse_date(r.get("日付", ""))
        if d is None:
            continue
        amount = parse_amount(r.get("取扱額"))
        persons = parse_count(r.get(col_persons))
        unit_price = parse_count(r.get(col_unit_price))
        amount_prev_actual = parse_amount(r.get("取扱額_比較年実績"))
        persons_prev_actual = parse_count(r.get(col_persons_prev_actual))
        amount_prev_reserved = parse_amount(r.get("取扱額_比較年予約"))
        persons_prev_reserved = parse_count(r.get(col_persons_prev_reserved))
        weekday = (r.get("曜日") or "").strip()

        daily.append({
            "date": d.isoformat(),
            "weekday": weekday,
            "amount_yen": amount,
            "persons": persons,
            "unit_price_yen": unit_price,
            "amount_prev_actual_yen": amount_prev_actual,
            "persons_prev_actual": persons_prev_actual,
        })

        if amount is None and persons is None:
            masked_days += 1
            continue

        counted_days += 1
        if amount is not None:
            total_amount += amount
        if persons is not None:
            total_persons += persons
        if amount_prev_actual is not None:
            total_amount_prev_actual += amount_prev_actual
        if persons_prev_actual is not None:
            total_persons_prev_actual += persons_prev_actual
        if amount_prev_reserved is not None:
            total_amount_prev_reserved += amount_prev_reserved
        if persons_prev_reserved is not None:
            total_persons_prev_reserved += persons_prev_reserved

        if weekday and persons is not None:
            weekday_persons.setdefault(weekday, []).append(persons)

        # comparable: 当年・前年ともに値がある日だけ加算（前年比の妥当な比較）
        if amount is not None and amount_prev_actual is not None and \
           persons is not None and persons_prev_actual is not None:
            cmp_total_amount += amount
            cmp_total_amount_prev += amount_prev_actual
            cmp_total_persons += persons
            cmp_total_persons_prev += persons_prev_actual
            cmp_days += 1

    # 曜日別集計
    weekday_order = ["月", "火", "水", "木", "金", "土", "日"]
    weekday_summary = []
    for w in weekday_order:
        ps = weekday_persons.get(w, [])
        weekday_summary.append({
            "weekday": w,
            "count_days": len(ps),
            "avg_persons": round(sum(ps) / len(ps), 1) if ps else None,
            "total_persons": sum(ps) if ps else 0,
        })

    avg_unit_price = safe_div(total_amount, total_persons)
    if avg_unit_price is not None:
        avg_unit_price = round(avg_unit_price)

    return {
        "daily": daily,
        "kpi": {
            "total_amount_yen": total_amount,
            "total_persons": total_persons,
            "unit_label": UNIT_LABEL[kind],
            "average_unit_price_yen": avg_unit_price,
            "counted_days": counted_days,
            "masked_days": masked_days,
        },
        "yoy": {
            "amount_yoy_ratio": safe_div(total_amount, total_amount_prev_actual),
            "persons_yoy_ratio": safe_div(total_persons, total_persons_prev_actual),
            "prev_actual_total_amount_yen": total_amount_prev_actual,
            "prev_actual_total_persons": total_persons_prev_actual,
            "prev_reserved_total_amount_yen": total_amount_prev_reserved,
            "prev_reserved_total_persons": total_persons_prev_reserved,
        },
        "comparable_yoy": {
            "note": "当年・前年ともに値がある日だけで合算した前年比（マスク日除外）",
            "comparable_days": cmp_days,
            "current_total_amount_yen": cmp_total_amount,
            "prev_total_amount_yen": cmp_total_amount_prev,
            "amount_yoy_ratio": safe_div(cmp_total_amount, cmp_total_amount_prev),
            "current_total_persons": cmp_total_persons,
            "prev_total_persons": cmp_total_persons_prev,
            "persons_yoy_ratio": safe_div(cmp_total_persons, cmp_total_persons_prev),
        },
        "weekday_summary": weekday_summary,
    }


# ---- 月次年間集計（lodging-annual.json 互換） --------------------------------

def build_annual_monthly(rows: list[dict], kind: str) -> dict:
    """index.html の LODGE_* 配列と同形式の月次集計を構築する。"""
    col_persons = COL_PERSONS[kind]
    # 月 → {amount_yen合計, persons合計}
    bucket: dict[str, dict] = {}
    for r in rows:
        d = parse_date(r.get("日付", ""))
        if d is None:
            continue
        m = f"{d.year:04d}-{d.month:02d}"
        amount = parse_amount(r.get("取扱額"))
        persons = parse_count(r.get(col_persons))
        b = bucket.setdefault(m, {"amount_yen": 0, "persons": 0})
        if amount is not None:
            b["amount_yen"] += amount
        if persons is not None:
            b["persons"] += persons

    months_sorted = sorted(bucket.keys())
    monthly = []
    for m in months_sorted:
        b = bucket[m]
        # 取扱額は「万円単位の四捨五入」（既存JSONの torihiki_man に合わせる）
        torihiki_man = round(b["amount_yen"] / 10000)
        jinpaku = b["persons"]
        tanka_yen = round(b["amount_yen"] / jinpaku) if jinpaku > 0 else 0
        monthly.append({
            "month": m,
            "torihiki_man": torihiki_man,
            "jinpaku": jinpaku,
            "tanka_yen": tanka_yen,
        })

    # サマリ（R6 = 最初の12ヶ月 / R7 = 次の12ヶ月）
    def sum_range(arr: list[dict], key: str, start: int, end: int) -> int:
        return sum(x[key] for x in arr[start:end])

    r6 = monthly[0:12]
    r7 = monthly[12:24] if len(monthly) >= 24 else monthly[12:]
    r6_torihiki = sum(x["torihiki_man"] for x in r6)
    r6_jinpaku = sum(x["jinpaku"] for x in r6)
    r6_tanka = round(r6_torihiki * 10000 / r6_jinpaku) if r6_jinpaku > 0 else 0
    r7_torihiki = sum(x["torihiki_man"] for x in r7)
    r7_jinpaku = sum(x["jinpaku"] for x in r7)
    r7_tanka = round(r7_torihiki * 10000 / r7_jinpaku) if r7_jinpaku > 0 else 0

    def pct(curr, prev):
        if not prev:
            return 0.0
        return round((curr - prev) / prev * 100, 1)

    summary = {
        "r6_torihiki_man": r6_torihiki,
        "r6_jinpaku": r6_jinpaku,
        "r6_tanka_yen": r6_tanka,
        "r7_torihiki_man": r7_torihiki,
        "r7_jinpaku": r7_jinpaku,
        "r7_tanka_yen": r7_tanka,
        "yoy_torihiki_pct": pct(r7_torihiki, r6_torihiki),
        "yoy_jinpaku_pct": pct(r7_jinpaku, r6_jinpaku),
        "yoy_tanka_pct": pct(r7_tanka, r6_tanka),
    }

    return {
        "event_id": "lodging-annual",
        "event_name": "じゃらん宿泊年間推移",
        "data_source": "じゃらんエリアダッシュボード (Tableau Cloud)",
        "period": f"{months_sorted[0]} 〜 {months_sorted[-1]} ({len(months_sorted)}ヶ月)" if months_sorted else "",
        "last_updated": datetime.now().astimezone().isoformat(timespec="seconds"),
        "monthly": monthly,
        "summary": summary,
    }


# ---- メイン ------------------------------------------------------------------

def main() -> int:
    parser = argparse.ArgumentParser(description="じゃらん予約日別データ集計")
    parser.add_argument("--input", required=True, help="入力CSVパス")
    parser.add_argument("--kind", required=True,
                        choices=[KIND_LODGING, KIND_EXPERIENCE],
                        help="lodging（宿泊）/ experience（遊び体験）")
    parser.add_argument("--event",
                        help="event-id（sns-events-meta.json から日付範囲を参照）")
    parser.add_argument("--period",
                        help="期間ID（--date-start/end 指定時の出力ファイル名用、例: 2026-04, fy2025）")
    parser.add_argument("--date-start", help="集計開始日 YYYY-MM-DD")
    parser.add_argument("--date-end", help="集計終了日 YYYY-MM-DD")
    parser.add_argument("--events-meta", default="data/events/sns-events-meta.json",
                        help="イベントメタJSONパス（--event 使用時、既定: data/events/sns-events-meta.json）")
    parser.add_argument("--output",
                        help="出力JSONパス（省略時は data/events/{kind}-{event-or-period}.json）")
    parser.add_argument("--print-daily", action="store_true",
                        help="標準出力に日別データの先頭10件を表示")
    parser.add_argument("--annual-monthly", action="store_true",
                        help="lodging-annual.json 互換の月次集計フォーマットで出力（kind=lodging想定）")
    args = parser.parse_args()

    # 日付範囲の決定
    period_id = args.period
    period_label = None
    if args.event:
        try:
            meta = load_event_meta(Path(args.events_meta), args.event)
        except (FileNotFoundError, KeyError) as e:
            print(f"ERROR: {e}", file=sys.stderr)
            return 2
        date_start = parse_date(meta["date_start"])
        date_end = parse_date(meta["date_end"])
        period_id = args.event
        period_label = meta.get("name", args.event)
    elif args.date_start and args.date_end:
        date_start = parse_date(args.date_start)
        date_end = parse_date(args.date_end)
    else:
        date_start = None
        date_end = None

    # CSV読み込み
    input_path = Path(args.input)
    if not input_path.exists():
        print(f"ERROR: 入力CSV {input_path} が見つかりません", file=sys.stderr)
        return 1

    rows_in_range: list[dict] = []
    with open(input_path, encoding="utf-8-sig", newline="") as f:
        # じゃらんCSVは先頭に "# ..." のコメント行があるので、これをスキップする
        lines = []
        header_found = False
        for raw in f:
            if not header_found:
                if raw.lstrip().startswith("#"):
                    continue
                header_found = True
            lines.append(raw)
        if not lines:
            print("ERROR: CSVにヘッダが見つかりません", file=sys.stderr)
            return 1
        reader = csv.DictReader(lines)
        # 必須列のチェック
        required = {"日付", "取扱額", COL_PERSONS[args.kind], COL_UNIT_PRICE[args.kind]}
        missing = required - set(reader.fieldnames or [])
        if missing:
            print(f"ERROR: CSVに必要な列がありません: {missing}", file=sys.stderr)
            print(f"  検出済の列: {reader.fieldnames}", file=sys.stderr)
            return 1
        for r in reader:
            d = parse_date(r.get("日付", ""))
            if d is None:
                continue
            if date_start and d < date_start:
                continue
            if date_end and d > date_end:
                continue
            rows_in_range.append(r)

    if not rows_in_range:
        print(
            f"WARNING: 集計対象行が0件です（日付範囲: {date_start}〜{date_end}）",
            file=sys.stderr,
        )

    # 集計
    result = aggregate(rows_in_range, args.kind)

    # 月次年間集計モード（lodging-annual.json 互換）
    if args.annual_monthly:
        annual = build_annual_monthly(rows_in_range, args.kind)
        if args.output:
            output_path = Path(args.output)
        else:
            output_path = Path("data/events/lodging-annual.json")
        output_path.parent.mkdir(parents=True, exist_ok=True)
        with open(output_path, "w", encoding="utf-8") as f:
            json.dump(annual, f, ensure_ascii=False, indent=2)
        print(f"=== 月次年間集計（lodging-annual.json 互換） ===")
        for m in annual["monthly"]:
            print(f"  {m['month']}: 取扱額 {m['torihiki_man']:,}万円 / 人泊 {m['jinpaku']:,} / 単価 {m['tanka_yen']:,}円")
        s = annual["summary"]
        print(f"R6: 取扱額 {s['r6_torihiki_man']:,}万円 / 人泊 {s['r6_jinpaku']:,} / 単価 {s['r6_tanka_yen']:,}円")
        print(f"R7: 取扱額 {s['r7_torihiki_man']:,}万円 / 人泊 {s['r7_jinpaku']:,} / 単価 {s['r7_tanka_yen']:,}円")
        print(f"前年比 取扱額 +{s['yoy_torihiki_pct']:.1f}% / 人泊 +{s['yoy_jinpaku_pct']:.1f}% / 単価 +{s['yoy_tanka_pct']:.1f}%")
        print(f"出力: {output_path}")
        return 0

    # 出力データ
    output_data = {
        "kind": args.kind,
        "period_id": period_id or "all",
        "period_label": period_label,
        "period": {
            "start": date_start.isoformat() if date_start else None,
            "end": date_end.isoformat() if date_end else None,
        },
        **result,
        "source": {
            "tool": "scripts/jaran-aggregate.py",
            "input_csv": str(input_path),
            "generated_at": datetime.now().isoformat(timespec="seconds"),
        },
    }

    # 出力パス
    if args.output:
        output_path = Path(args.output)
    else:
        pid = period_id or "all"
        output_path = Path(f"data/events/{args.kind}-{pid}.json")
    output_path.parent.mkdir(parents=True, exist_ok=True)
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(output_data, f, ensure_ascii=False, indent=2)

    # サマリー
    kpi = result["kpi"]
    yoy = result["yoy"]
    cyoy = result["comparable_yoy"]
    print(f"=== じゃらん集計結果（{args.kind}） ===")
    print(f"対象期間 : {date_start} 〜 {date_end}")
    print(f"対象日数 : {kpi['counted_days']}日（マスク {kpi['masked_days']}日）")
    print(
        f"取扱額   : {kpi['total_amount_yen']:,}円  "
        f"前年比 {fmt_ratio(yoy['amount_yoy_ratio'])} "
        f"[比較可日のみ: {fmt_ratio(cyoy['amount_yoy_ratio'])} / "
        f"{cyoy['comparable_days']}日]"
    )
    print(
        f"{kpi['unit_label']}数    : {kpi['total_persons']:,}{kpi['unit_label']}  "
        f"前年比 {fmt_ratio(yoy['persons_yoy_ratio'])} "
        f"[比較可日のみ: {fmt_ratio(cyoy['persons_yoy_ratio'])} / "
        f"{cyoy['comparable_days']}日]"
    )
    if kpi["average_unit_price_yen"]:
        print(f"平均単価 : {kpi['average_unit_price_yen']:,}円")
    print(f"出力     : {output_path}")
    if args.print_daily:
        print("---- daily（先頭10件）----")
        for d in result["daily"][:10]:
            print(d)
    return 0


if __name__ == "__main__":
    sys.exit(main())
