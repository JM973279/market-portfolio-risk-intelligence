"use client";
import { useEffect, useId, useRef, useState } from "react";
import { useDashboard } from "@/components/dashboard-shell";
import type { Asset } from "@/lib/portfolio-api";
import styles from "./portfolio.module.css";

const normalize = (text: string) => text.normalize("NFKC").trim().toLocaleLowerCase();
export function AssetSearch({ assets, value, label, onChange }: { assets: Asset[]; value: string; label: string; onChange: (ticker: string) => void }) {
 const { language } = useDashboard();
 const ko = language === "ko";
 const id = useId();
 const list = useRef<HTMLUListElement>(null);
 const [query, setQuery] = useState("");
 const [open, setOpen] = useState(false);
 const [active, setActive] = useState(0);
 const [market, setMarket] = useState("");
 const [kind, setKind] = useState("");
 const [status, setStatus] = useState("");
 const reasonLabel = (code: string) => {
  const labels: Record<string, [string, string]> = {
   RIGHTS_UNCONFIRMED: ["공개 데이터 사용 권리가 확인되지 않았습니다", "Public data usage rights are unconfirmed"],
   NO_APPROVED_RELEASE: ["승인된 데이터 스냅샷이 없습니다", "No approved data snapshot"],
   INVALID_PRICE_WINDOW: ["검증된 757개 가격이 부족하거나 유효하지 않습니다", "757 validated prices are missing or invalid"],
   FACTOR_POLICY_OR_COVERAGE_UNVERIFIED: ["팩터 데이터와 방법론 검증이 필요합니다", "Factor data and policy require verification"],
  };
  return labels[code]?.[ko ? 0 : 1] ?? code;
 };
 const q = normalize(query);
 const results = assets.filter(a => (!market || a.market === market) && (!kind || a.type === kind) && (!status || a.support_status === status) && [a.ticker, a.name, a.name_ko ?? "", ...(a.aliases ?? [])].some(s => normalize(s).includes(q)))
  .sort((a,b) => {
   const rank = (a: Asset) => normalize(a.ticker) === q ? 0 : normalize(a.ticker).startsWith(q) ? 1 : [a.name,a.name_ko ?? ""].some(n => normalize(n).startsWith(q)) ? 2 : 3;
   return rank(a)-rank(b);
  }).slice(0, 30);
 useEffect(() => { list.current?.querySelector(`[aria-selected="true"]`)?.scrollIntoView({ block: "nearest" }); }, [active, query, market, kind, status]);
 const selected = assets.find(a => a.ticker === value);
 const choose = (asset: Asset) => { if (asset.selectable !== true || asset.support_scope !== "frozen_v1_only") return; onChange(asset.ticker); setQuery(""); setOpen(false); };
 return <div className={styles.search} onBlur={e => { if (!e.currentTarget.contains(e.relatedTarget)) setOpen(false); }}>
  <input role="combobox" aria-label={label} aria-expanded={open} aria-controls={`${id}-list`} aria-autocomplete="list" aria-activedescendant={open && results[active] ? `${id}-${active}` : undefined}
   value={open ? query : selected ? `${selected.ticker} · ${ko ? selected.name_ko : selected.name}` : value}
   placeholder={ko ? "티커·회사명 검색" : "Search ticker or company"}
   onFocus={() => { setOpen(true); setActive(0); }}
   onChange={e => { setQuery(e.target.value); setActive(0); setOpen(true); if(value) onChange(""); }}
   onKeyDown={e => {
    if(e.key === "Escape") setOpen(false);
    if(e.key === "ArrowDown" || e.key === "ArrowUp") { e.preventDefault(); setOpen(true); setActive(i => Math.max(0, Math.min(results.length-1, i+(e.key === "ArrowDown" ? 1 : -1)))); }
    if(e.key === "Enter" && open) { e.preventDefault(); if(results[active]) choose(results[active]); }
   }}/>
  {open && <div className={styles.searchPopup}>
   <div className={styles.searchFilters}>
    <select aria-label={ko ? "시장" : "Market"} value={market} onChange={e => {setMarket(e.target.value);setActive(0);}}><option value="">{ko ? "전체 시장" : "All markets"}</option><option>US</option><option>KR</option></select>
    <select aria-label={ko ? "자산 유형" : "Asset type"} value={kind} onChange={e => {setKind(e.target.value);setActive(0);}}><option value="">{ko ? "전체 유형" : "All types"}</option><option value="stock">{ko ? "주식" : "Stock"}</option><option value="etf">ETF</option></select>
    <select aria-label={ko ? "지원 상태" : "Support status"} value={status} onChange={e => {setStatus(e.target.value);setActive(0);}}><option value="">{ko ? "전체 상태" : "All statuses"}</option>{["full","partial","unsupported"].map(s => <option key={s}>{s}</option>)}</select>
   </div>
   <ul ref={list} id={`${id}-list`} role="listbox" aria-label={label}>
    {results.map((a,i) => <li id={`${id}-${i}`} key={a.asset_id ?? a.ticker} role="option" aria-selected={i === active} aria-disabled={!a.selectable || a.support_scope !== "frozen_v1_only"} onMouseDown={e => e.preventDefault()} onClick={() => choose(a)}>
     <b>{a.ticker}</b> · {ko ? a.name_ko : a.name} <small>{a.market} · {a.currency} · {a.support_status}</small>
     {(!a.selectable || a.support_scope !== "frozen_v1_only") && <small>{ko ? "분석 불가: " : "Unavailable: "}{a.reason_codes?.map(reasonLabel).join(" · ") || (ko ? "승인된 분석 경로 없음" : "No approved analysis route")}</small>}
    </li>)}
   </ul>
   <p role="status">{results.length ? (ko ? "최대 30개 결과 · 고정 V1 지원" : "Up to 30 results · Frozen V1 support") : (ko ? "결과 없음 · 승인된 카탈로그에 없는 종목은 분석할 수 없습니다." : "No results. Assets outside the approved catalog cannot be analyzed.")}</p>
  </div>}
 </div>;
}
