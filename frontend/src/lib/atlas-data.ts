import { rangeStart, timestamp, type ChartRange } from "./chart-data";
import type { GlobalData, MonitorData } from "./dashboard-types";

export const breadthSignals = [
 { key:"decline_1d_breadth", ko:"하락 종목", en:"Declining stocks" },
 { key:"loss_2pct_1d_breadth", ko:"일간 하락률 2% 이상", en:"Daily decline ≥2%" },
 { key:"loss_5pct_5d_breadth", ko:"5회 관측 하락률 5% 이상", en:"5-observation decline ≥5%" },
 { key:"drawdown_10pct_breadth", ko:"고점 대비 하락률 10% 이상", en:"Drawdown ≥10%" },
 { key:"high_vol_breadth", ko:"고변동성 종목", en:"High volatility" },
 { key:"abnormal_volume_breadth", ko:"거래량 급증 종목", en:"Unusual volume" },
] as const;
export type AtlasWindow = [number, number];
export function atlasDates(global: GlobalData, monitor: MonitorData | null): string[] {
 const end = global.asOf;
 return [...new Set([...global.us.map(p=>p.date), ...global.korea.map(p=>p.date), ...(monitor?.history.map(r=>r.Date) ?? [])])]
  .filter(day => Number.isFinite(timestamp(day)) && (!end || day <= end)).sort();
}
export function nearestDateIndex(dates: string[], day: string): number {
 if (!dates.length || !Number.isFinite(timestamp(day))) return 0;
 const time = timestamp(day);
 let low = 0, high = dates.length - 1;
 while (low < high) { const mid = Math.floor((low+high)/2); if(timestamp(dates[mid])<time)low=mid+1;else high=mid; }
 return low>0 && Math.abs(timestamp(dates[low-1])-time)<=Math.abs(timestamp(dates[low])-time) ? low-1 : low;
}
export function clampAtlasWindow(dates: string[], first: number, last: number): AtlasWindow {
 if (dates.length < 2) return [0,0];
 const a=Math.min(dates.length-2,Math.max(0,Math.floor(Math.min(first,last))));
 const b=Math.min(dates.length-1,Math.max(a+1,Math.floor(Math.max(first,last))));
 return [a,b];
}
export function atlasRange(dates: string[], range: ChartRange): AtlasWindow {
 if (!dates.length) return [0,0];
 const start = new Date(rangeStart(dates.at(-1)!,range,dates[0])).toISOString().slice(0,10);
 return clampAtlasWindow(dates,nearestDateIndex(dates,start),dates.length-1);
}
// Values are preserved exactly. No percentile recomputation or missing-value fill.
export function breadthValue(row: MonitorData["history"][number] | undefined, key: string): number | null {
 const value = row?.[key];
 return typeof value === "number" && Number.isFinite(value) ? value : null;
}
export function breadthColor(value: number | null): string {
 if (value === null) return "transparent";
 if (value >= .9) return "#F3B54A";
 return `rgba(105,200,245,${.1+Math.max(0,Math.min(1,value))*.62})`;
}
