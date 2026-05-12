/**
 * fetch-weather.ts
 *
 * Open-Meteo Historical Weather API から、米沢の各イベント期間（±buffer日）の
 * 過去日次気象データを取得し、data/events/weather.json に集約保存する。
 *
 * 実行: npm run fetch:weather
 *      （プロジェクトルートから tsx で起動される前提）
 *
 * 出典: https://open-meteo.com/en/docs/historical-weather-api
 */

import { readFileSync, writeFileSync, mkdirSync } from 'fs';
import { join, dirname } from 'path';

const ROOT = process.cwd();
const META_PATH = join(ROOT, 'data/events/event-meta.json');
const OUT_PATH = join(ROOT, 'data/events/weather.json');
const API_BASE = 'https://archive-api.open-meteo.com/v1/archive';

interface EventMeta {
  id: string;
  name: string;
  month: number;
  period_start_mmdd: string;
  period_end_mmdd: string;
  buffer_days: number;
}

interface FiscalYear {
  id: string;        // 'R6', 'R7', ...
  calendar_offset: number; // 0 for R6 (FY starts 2024), 1 for R7 (2025), ...
}

interface MetaFile {
  location: { name: string; lat: number; lon: number; address: string; timezone: string };
  events: EventMeta[];
  fiscal_years: FiscalYear[];
}

interface Period {
  fiscal_year: string;
  start: string; // YYYY-MM-DD
  end: string;
}

interface DailyEntry {
  date: string;
  tmax: number | null;
  tmin: number | null;
  precip_mm: number | null;
  weather_code: number | null;
  weather_label: string;
  snowfall_cm: number | null;
  wind_max_kmh: number | null;
}

// WMO Weather interpretation codes
// https://open-meteo.com/en/docs (Weather codes section)
const WMO_LABELS: Record<number, string> = {
  0: '快晴',
  1: 'おおむね晴れ',
  2: '晴れ時々曇り',
  3: '曇り',
  45: '霧',
  48: '着氷性の霧',
  51: '霧雨（弱）',
  53: '霧雨（中）',
  55: '霧雨（強）',
  56: '着氷性霧雨（弱）',
  57: '着氷性霧雨（強）',
  61: '雨（弱）',
  63: '雨（中）',
  65: '雨（強）',
  66: '凍雨（弱）',
  67: '凍雨（強）',
  71: '雪（弱）',
  73: '雪（中）',
  75: '雪（強）',
  77: '雪粒',
  80: 'にわか雨（弱）',
  81: 'にわか雨（中）',
  82: 'にわか雨（強）',
  85: 'にわか雪（弱）',
  86: 'にわか雪（強）',
  95: '雷雨',
  96: '雷雨・雹（弱）',
  99: '雷雨・雹（強）',
};

function wmoLabel(code: number | null | undefined): string {
  if (code == null) return '不明';
  return WMO_LABELS[code] ?? `不明（code:${code}）`;
}

function jstISOString(d: Date = new Date()): string {
  const jst = new Date(d.getTime() + 9 * 60 * 60 * 1000);
  return jst.toISOString().slice(0, -1) + '+09:00';
}

function expandFiscalYears(ev: EventMeta, fiscalYears: FiscalYear[]): Period[] {
  // R6 fiscal year starts 2024-04. fiscal_years[i].calendar_offset adjusts from there.
  const FY_BASE_YEAR = 2024; // R6 base
  const periods: Period[] = [];
  for (const fy of fiscalYears) {
    const fyStartYear = FY_BASE_YEAR + fy.calendar_offset;
    // For event months April-Dec, the event is in fyStartYear.
    // For Jan-Mar, the event is in fyStartYear+1 (still within the fiscal year).
    const calendarYear = ev.month >= 4 ? fyStartYear : fyStartYear + 1;
    const [sm, sd] = ev.period_start_mmdd.split('-').map(Number);
    const [em, ed] = ev.period_end_mmdd.split('-').map(Number);
    const startDate = new Date(Date.UTC(calendarYear, sm - 1, sd));
    const endDate = new Date(Date.UTC(calendarYear, em - 1, ed));
    // Apply buffer
    startDate.setUTCDate(startDate.getUTCDate() - ev.buffer_days);
    endDate.setUTCDate(endDate.getUTCDate() + ev.buffer_days);
    const fmt = (d: Date) => d.toISOString().slice(0, 10);
    periods.push({ fiscal_year: fy.id, start: fmt(startDate), end: fmt(endDate) });
  }
  return periods;
}

async function fetchPeriod(lat: number, lon: number, tz: string, start: string, end: string): Promise<DailyEntry[]> {
  const params = new URLSearchParams({
    latitude: String(lat),
    longitude: String(lon),
    start_date: start,
    end_date: end,
    daily:
      'temperature_2m_max,temperature_2m_min,precipitation_sum,weather_code,snowfall_sum,wind_speed_10m_max',
    timezone: tz,
  });
  const url = `${API_BASE}?${params}`;
  console.log(`    GET ${start} .. ${end}`);
  const res = await fetch(url);
  if (!res.ok) {
    const text = await res.text();
    throw new Error(`Open-Meteo API error ${res.status}: ${text.slice(0, 300)}`);
  }
  const json: any = await res.json();
  const time: string[] = json.daily?.time ?? [];
  const days: DailyEntry[] = [];
  for (let i = 0; i < time.length; i++) {
    const code = json.daily.weather_code?.[i] ?? null;
    days.push({
      date: time[i],
      tmax: json.daily.temperature_2m_max?.[i] ?? null,
      tmin: json.daily.temperature_2m_min?.[i] ?? null,
      precip_mm: json.daily.precipitation_sum?.[i] ?? null,
      weather_code: code,
      weather_label: wmoLabel(code),
      snowfall_cm: json.daily.snowfall_sum?.[i] ?? null,
      wind_max_kmh: json.daily.wind_speed_10m_max?.[i] ?? null,
    });
  }
  return days;
}

async function sleep(ms: number) {
  return new Promise((r) => setTimeout(r, ms));
}

async function main() {
  console.log('米沢イベント期間 天気データ取得開始');
  const meta: MetaFile = JSON.parse(readFileSync(META_PATH, 'utf-8'));
  const { lat, lon, timezone } = meta.location;
  const today = new Date();

  const result: any = {
    source: 'Open-Meteo Historical Weather API',
    api_url: API_BASE,
    location: meta.location,
    last_updated: jstISOString(today),
    note: '各イベント期間±1日の日次気象データ。R8（2026年度）など未来期間は取得対象外（履歴APIのため）。',
    events: {} as Record<string, any>,
  };

  for (const ev of meta.events) {
    console.log(`\n[Event] ${ev.name} (${ev.id})`);
    const periods = expandFiscalYears(ev, meta.fiscal_years);
    const eventOut: any = {
      event_name: ev.name,
      core_period: { start_mmdd: ev.period_start_mmdd, end_mmdd: ev.period_end_mmdd },
      buffer_days: ev.buffer_days,
      periods: [] as any[],
    };
    for (const p of periods) {
      // 履歴APIは過去のみ。endが今日以降の期間はスキップ。
      if (new Date(p.start) >= today) {
        console.log(`  Skip ${p.fiscal_year} (${p.start} は未来)`);
        continue;
      }
      const effectiveEnd = new Date(p.end) >= today ? new Date(today.getTime() - 2 * 24 * 3600 * 1000).toISOString().slice(0, 10) : p.end;
      const daily = await fetchPeriod(lat, lon, timezone, p.start, effectiveEnd);
      eventOut.periods.push({
        fiscal_year: p.fiscal_year,
        start: p.start,
        end: effectiveEnd,
        daily,
      });
      await sleep(500); // be polite
    }
    result.events[ev.id] = eventOut;
  }

  mkdirSync(dirname(OUT_PATH), { recursive: true });
  writeFileSync(OUT_PATH, JSON.stringify(result, null, 2) + '\n', 'utf-8');
  const totalDays = Object.values(result.events).reduce(
    (acc: number, e: any) => acc + e.periods.reduce((s: number, p: any) => s + p.daily.length, 0),
    0
  );
  console.log(`\n書き出し完了: ${OUT_PATH}`);
  console.log(`  events: ${Object.keys(result.events).length}, total daily records: ${totalDays}`);
}

main().catch((err) => {
  console.error('ERROR:', err);
  process.exit(1);
});
