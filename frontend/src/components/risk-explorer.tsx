"use client";
import { useEffect, useId, useState } from "react";
import Link from "next/link";
import { useDashboard } from "./dashboard-shell";
import { chartRanges, rangeStart, timestamp, type ChartRange } from "@/lib/chart-data";
import { finiteValue, metricDomain, observationAt, signalPath, type RiskMetric } from "@/lib/risk-explorer";
import { currentOperationalPoint } from "@/lib/operational-status";
import type { MarketPoint } from "@/lib/dashboard-types";

export default function RiskExplorer() {
 const { global, language, t } = useDashboard();
 const ko = language === "ko";
 const [range, setRange] = useState<ChartRange>("6M");
 const [metric, setMetric] = useState<RiskMetric>("risk");
 const [inspected, setInspected] = useState<string | null>(null);
 const [restored, setRestored] = useState(false);
 const [compact, setCompact] = useState(false);
 useEffect(() => {
  const media = window.matchMedia("(max-width:760px)");
  const update = () => setCompact(media.matches);
  const timer = setTimeout(update, 0);
  media.addEventListener("change", update);
  return () => {clearTimeout(timer);media.removeEventListener("change", update);};
 }, []);
 const clipId = useId().replaceAll(":", "");
 useEffect(() => {
  const timer = setTimeout(() => {
   try {
    const saved = JSON.parse(sessionStorage.getItem("mpri-explorer") ?? "null");
    if (chartRanges.includes(saved?.range)) setRange(saved.range);
    if (saved?.metric === "risk" || saved?.metric === "msi") setMetric(saved.metric);
   } catch { /* Preferences are optional. */ }
   setRestored(true);
  }, 0);
  return () => clearTimeout(timer);
 }, []);
 useEffect(() => { if (restored) { try { sessionStorage.setItem("mpri-explorer", JSON.stringify({ range, metric })); } catch { /* Optional. */ } } }, [range, metric, restored]);
 const end = global?.asOf;
 if (!end || !global) return <section className="panel explorer empty-state"><h2>Risk Explorer</h2><p>{t("noSeries")}</p></section>;
 const first = [global.us[0]?.date, global.korea[0]?.date].filter(Boolean).sort()[0] ?? end;
 const start = rangeStart(end, range, first);
 const shown = (points: MarketPoint[]) => points.filter(p => timestamp(p.date) >= start && p.date <= end);
 const lanes = [{ key: "us", name: ko ? "미국" : "United States", points: shown(global.us), color: "var(--ice)" }, { key: "korea", name: ko ? "한국" : "South Korea", points: shown(global.korea), color: "var(--silver)" }] as const;
 const dates = [...new Set(lanes.flatMap(l => l.points.map(p => p.date)))].sort();
 const day = inspected && dates.includes(inspected) ? inspected : dates.at(-1) ?? end;
 const chartWidth = compact ? 600 : 960, chartHeight = compact ? 450 : 370;
 const left = compact ? 44 : 54, right = chartWidth - 30, plotWidth = right - left;
 const x = (date: string) => left + (timestamp(date) - start) / Math.max(1, timestamp(end) - start) * plotWidth;
 const format = (value: number | null | undefined) => finiteValue(value) === null ? "N/A" : metric === "risk" ? `${(value! * 100).toFixed(1)}%` : value!.toFixed(3);
 return <section className="panel explorer" aria-label={ko ? "시장 신호 탐색" : "Market signal explorer"}>
  <div className="panel-header explorer-header"><div><span className="section-index">01 / SIGNAL TRAJECTORY</span><h2>{ko ? "위험 신호의 흐름" : "Risk, through time"}</h2></div><div className="explorer-controls"><div className="small-toggle" role="group" aria-label={ko ? "탐색 지표" : "Explorer metric"}><button aria-pressed={metric === "risk"} onClick={() => setMetric("risk")}>Risk Score</button><button aria-pressed={metric === "msi"} onClick={() => setMetric("msi")}>MSI</button></div><div className="range-toggle" role="group" aria-label={t("dateRange")}>{chartRanges.map(r => <button key={r} aria-pressed={range === r} onClick={() => { setRange(r); setInspected(null); }}>{r}</button>)}</div></div></div>
  <p className="explorer-note">{ko ? "독립 모델 · 같은 날짜를 따라 탐색하세요. 점수 차이를 시장 간 위험의 크기 차이로 해석하지 마세요." : "Independent models, aligned dates. Score differences do not measure relative market risk."}</p>
  <div className="explorer-lane-labels"><span>{metric === "risk" ? (ko ? "과거 OOS · Risk Score (10D)" : "Historical OOS · Risk Score (10D)") : (ko ? "저장된 관측 MSI · 시장별 개별 축" : "Stored observed MSI · separate scales")}</span><span><i className="legend-dash"/>{metric === "risk" ? "0.50" : (ko ? "날짜별 공식 임계값" : "Date-specific official threshold")}</span></div>
  <svg className="explorer-chart" viewBox={`0 0 ${chartWidth} ${chartHeight}`} role="img" aria-label={ko ? "미국과 한국의 독립 신호 시계열. 결측은 공백으로 표시." : "Independent US and Korea signal trajectories. Missing data remains blank."} onPointerMove={e => {
   if (!dates.length) return;
   const rect = e.currentTarget.getBoundingClientRect();
   const point = start + ((e.clientX - rect.left) / rect.width * chartWidth - left) / plotWidth * (timestamp(end) - start);
   setInspected(dates.reduce((a, b) => Math.abs(timestamp(a) - point) <= Math.abs(timestamp(b) - point) ? a : b));
  }}>
   {lanes.map((lane, i) => {
    const top = (compact ? 30 : 25) + i * (compact ? 200 : 166), laneHeight = compact ? 155 : 125, bottom = top + laneHeight;
    const [min, max] = metricDomain(lane.points, metric);
    const y = (value: number) => bottom - (value - min) / (max - min) * (laneHeight - 13);
    const active = observationAt(lane.points, day);
    const value = active?.[metric];
    return <g key={lane.key}>
     <defs><clipPath id={`${clipId}-${lane.key}`}><rect x={left} y={top} width={plotWidth} height={laneHeight}/></clipPath></defs>
     {[0, .5, 1].map(n => <g key={n}><line x1={left} x2={right} y1={y(min + n * (max - min))} y2={y(min + n * (max - min))} className="chart-gridline"/><text x={left - 12} y={y(min + n * (max - min)) + 4} textAnchor="end">{metric === "risk" ? `${Math.round(n * 100)}` : (min + n * (max - min)).toFixed(1)}</text></g>)}
     <g clipPath={`url(#${clipId}-${lane.key})`}>
      {lane.points.filter(p => p.stress === 1).map(p => <rect key={p.date} x={x(p.date)} y={top} width="3" height={laneHeight} fill="var(--amber)" opacity=".12"/>)}
      {metric === "risk" ? <line x1={left} x2={right} y1={y(.5)} y2={y(.5)} className="threshold-line"/> : <path d={signalPath(lane.points, "threshold", x, y)} className="threshold-line" fill="none"/>}
      <path d={signalPath(lane.points, metric, x, y)} stroke={lane.color} strokeWidth="2" strokeLinejoin="round" fill="none"/>
      <line x1={x(day)} x2={x(day)} y1={top} y2={bottom} stroke="var(--muted)" strokeDasharray="3 5"/>
      {finiteValue(value) !== null && <circle cx={x(day)} cy={y(value!)} r="4" fill={lane.color} stroke="var(--canvas)" strokeWidth="2"/>}
     </g>
     <text x={left + 2} y={top + 5} className="lane-name">{lane.name.toUpperCase()}</text>
    </g>;
   })}
   {(compact ? [0, .5, 1] : [0, .25, .5, .75, 1]).map(n => <text key={n} x={left + n * plotWidth} y={chartHeight - 5} textAnchor={n === 0 ? "start" : n === 1 ? "end" : "middle"}>{new Date(start + n * (timestamp(end) - start)).toISOString().slice(0, 10)}</text>)}
  </svg>
  <div className="explorer-readout" aria-live="polite"><time>{day}</time>{lanes.map(lane => <span key={lane.key}>{lane.name}<b style={{ color: lane.color }}>{format(observationAt(lane.points, day)?.[metric])}</b></span>)}<span className="readout-scope">{ko ? "과거 연구 관측" : "Historical research"}</span></div>
  {dates.length > 0 && <label className="chart-slider-label"><span>{t("inspectDate")}</span><input aria-label={ko ? "양시장 관측일 탐색" : "Explore market observation date"} type="range" min="0" max={dates.length - 1} value={Math.max(0, dates.indexOf(day))} onChange={e => setInspected(dates[Number(e.target.value)])}/></label>}
  <p className="panel-note">{ko ? "옅은 황색 세로선은 원본에 저장된 스트레스 관측입니다. 새 위험 지표나 실시간 신호가 아닙니다." : "Faint amber marks are stored stress observations, not a new indicator or live signal."} {t("gaps")}</p>
 </section>;
}

export function CurrentObservationRail() {
 const { operational, language } = useDashboard();
 const ko = language === "ko";
 return <aside className="observation-rail"><div className="rail-heading"><span className="section-index">OBSERVATION DESK</span><h2>{ko ? "현재 확인된 신호" : "The observation desk"}</h2><p>{ko ? "연구 시계열과 별도로 수집·검증한 운영 스냅샷" : "Verified operational snapshots, separate from historical series"}</p></div>{(["us", "korea"] as const).map(country => {
  const source = operational?.markets[country];
  const current = currentOperationalPoint(source);
  return <article key={country} className={`observation-row ${current ? "verified" : "unavailable"}`}><div className="observation-market"><Link href={`/${country}`}>{country === "us" ? (ko ? "미국 시장" : "US market") : (ko ? "한국 시장" : "Korea market")} ↗</Link><span className={`status-chip ${current ? "available" : "unknown"}`}>{current ? (ko ? "관측 확인" : "VERIFIED") : (ko ? "점수 미확인" : "UNAVAILABLE")}</span></div><div className="observation-score"><strong>{current?.risk == null ? "N/A" : `${(current.risk * 100).toFixed(1)}%`}</strong><span>Risk Score · 10D</span></div><div className="observation-secondary"><span>MSI <b>{current?.msi?.toFixed(3) ?? "N/A"}</b></span><span>{ko ? "공식 임계값" : "Threshold"} <b>{current?.threshold?.toFixed(3) ?? "N/A"}</b></span></div><time>{source?.expectedDate ?? "N/A"}</time>{!current && <p>{ko ? "최신 검증을 통과하지 못했습니다. 과거 점수를 현재 값으로 이월하지 않습니다." : "Current validation did not pass. Historical scores are not carried forward."}</p>}</article>;
 })}<p className="rail-footnote">{ko ? "수동 갱신 스냅샷 · 실시간 피드 없음 · 보정된 손실확률 아님" : "Manually refreshed snapshots · no live feed · not a calibrated loss probability"}</p></aside>;
}
