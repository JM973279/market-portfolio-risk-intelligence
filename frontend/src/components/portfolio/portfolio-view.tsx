"use client";
import { useEffect, useRef, useState } from "react";
import Link from "next/link";
import { useDashboard } from "@/components/dashboard-shell";
import { CountryCards } from "@/components/research-panels";
import { PORTFOLIO_API, PortfolioApiError, analyzePortfolio, comparePortfolios, exampleAfter, exampleBefore, getScenarios, getUniverse, inputProblem, type Analysis, type Comparison, type Holding, type Scenarios, selectablePortfolio, type Catalog } from "@/lib/portfolio-api";
import { HiddenRiskMap, HoldingsEditor, StressTest, WhatIfTable, usePortfolioCopy } from "./portfolio-panels";
import styles from "./portfolio.module.css";

const DEFAULT_VALUE = 100_000;
type Task = "analyze" | "compare";
const toApiError = (e: unknown) => (e instanceof PortfolioApiError ? e : new PortfolioApiError("network", PORTFOLIO_API));

function ApiProblem({ error }: { error: PortfolioApiError }) {
 const p = usePortfolioCopy();
 const key = error.kind === "network" ? "apiDown" : error.kind === "unavailable" ? "apiUnavailable" : "apiRejected";
 return <section className={`panel ${styles.alert} ${styles.section}`} role="alert"><h2>{p(key)}</h2><p>{p("apiRetry")}</p></section>;
}

export default function PortfolioView() {
 const p = usePortfolioCopy();
 const { global, operational, language } = useDashboard();
 const revision = useRef(0);
 const [workspace, setWorkspace] = useState<"diagnosis" | "scenarios" | "whatif">("diagnosis");
 const [editor, setEditor] = useState<"current" | "proposed">("current");
 const [universe, setUniverse] = useState<Catalog | null>(null);
 const [scenarios, setScenarios] = useState<Scenarios | null>(null);
 const [holdings, setHoldings] = useState<Holding[]>(exampleBefore);
 const [proposed, setProposed] = useState<Holding[]>(exampleAfter);
 const [value, setValue] = useState(DEFAULT_VALUE);
 const [analysis, setAnalysis] = useState<Analysis | null>(null);
 const [comparison, setComparison] = useState<Comparison | null>(null);
 const [busy, setBusy] = useState<Task | null>("analyze");
 const [error, setError] = useState<{ task: Task; error: PortfolioApiError } | null>(null);

 // Load the asset list, scenarios and the example portfolio once the page is in the browser.
 useEffect(() => {
  let active = true;
  const initialRevision = revision.current;
  Promise.allSettled([getUniverse(), getScenarios(), analyzePortfolio(exampleBefore, DEFAULT_VALUE)])
   .then(([u, s, a]) => {
    if (!active) return;
    if (u.status === "fulfilled") setUniverse(u.value);
    if (s.status === "fulfilled") setScenarios(s.value);
    if (revision.current === initialRevision) {
     if (a.status === "fulfilled") setAnalysis(a.value);
     const failed = [u, s, a].find(result => result.status === "rejected");
     if (failed?.status === "rejected") setError({task:"analyze", error:toApiError(failed.reason)});
    }
   }).finally(() => { if (active) setBusy(null); });
  return () => { active = false; };
 }, []);

 const changeCurrent = (next: Holding[]) => { revision.current++; setHoldings(next); setAnalysis(null); setComparison(null); setError(null); };
 const changeValue = (next: number) => { revision.current++; setValue(next); setAnalysis(null); setComparison(null); setError(null); };
 const changeProposed = (next: Holding[]) => { revision.current++; setProposed(next); setComparison(null); setError(null); };
 const revealResults = () => {
  if (window.matchMedia("(max-width:760px)").matches) requestAnimationFrame(() => {
   document.getElementById("portfolio-results")?.scrollIntoView({block:"start",behavior:window.matchMedia("(prefers-reduced-motion:reduce)").matches ? "instant" : "smooth"});
  });
 };
 const run = async (task: Task) => {
  const started = revision.current;
  setBusy(task);
  setComparison(null);
  if (task === "analyze") setAnalysis(null);
  setError(null);
  try {
   if (task === "analyze") {
    const result = await analyzePortfolio(holdings, value);
    if (revision.current === started) {setAnalysis(result);revealResults();}
   } else {
    const result = await comparePortfolios(holdings, proposed, value);
    if (revision.current === started) { setAnalysis(result.current); setComparison(result);revealResults(); }
   }
  } catch (e) {
   if (revision.current === started) setError({ task, error: toApiError(e) });
  } finally {
   setBusy(null);
  }
 };

 const assets = universe?.assets ?? [];
 const network = error && error.error.kind !== "rejected" ? error.error : null;
 // Same date the U.S. card shows: the operational source date when present, else the research snapshot.
 const marketAsOf = operational?.markets.us.expectedDate ?? global?.asOf ?? null;
 const portfolioAsOf = analysis?.as_of ?? scenarios?.as_of ?? null;
 const ko = language === "ko";
 const currentValid = inputProblem(holdings, value) === null && universe !== null && selectablePortfolio(holdings, assets);
 const proposedValid = inputProblem(proposed, value) === null && universe !== null && selectablePortfolio(proposed, assets);
 const tabs = [{id:"diagnosis",label:ko?"위험 진단":"Risk diagnosis"},{id:"scenarios",label:ko?"스트레스 시나리오":"Stress scenarios"},{id:"whatif",label:ko?"What-if 비교":"What-if comparison"}] as const;
 const tabTo = (id: typeof workspace) => {setWorkspace(id); if(id !== "whatif") setEditor("current");};
 return <main id="main-content" tabIndex={-1} className="dashboard-content view-portfolio">
  <div className="page-hero compact-hero workspace-hero"><div className="hero-copy"><p className="eyebrow">PORTFOLIO / RESEARCH WORKSPACE</p><h1>{ko ? "포트폴리오, 더 깊이 들여다보다." : "Know what drives your portfolio."}</h1><p className="hero-subtitle">{p("subtitle")}</p></div><div className="hero-status"><span>{p("dataAsOf")} <b>{portfolioAsOf ?? "N/A"}</b></span><span className="live-label"><i/>Frozen V1 · {ko ? "28개 지원" : "28 supported assets"}</span></div></div>
  <div className={styles.workspaceGrid}>
   <aside className={`panel ${styles.holdingsPanel}`} aria-label={p("inputTitle")}>
    <div className="panel-header"><div><span className="section-index">HOLDINGS EDITOR</span><h2>{p("inputTitle")}</h2></div><span className="tag">USD</span></div>
    <p className="panel-note">{p("inputNote")}</p>
    {workspace === "whatif" && <div className={`small-toggle ${styles.editorToggle}`} role="group" aria-label={ko ? "편집할 포트폴리오" : "Portfolio to edit"}><button aria-pressed={editor === "current"} onClick={() => setEditor("current")}>{p("current")}</button><button aria-pressed={editor === "proposed"} onClick={() => setEditor("proposed")}>{p("proposed")}</button></div>}
    <HoldingsEditor label={p(editor)} holdings={editor === "current" ? holdings : proposed} onChange={editor === "current" ? changeCurrent : changeProposed} assets={assets} value={value}/>
    <label className={styles.valueField}>{p("valueLabel")}<input type="number" inputMode="decimal" min="0" step="1000" value={Number.isFinite(value) ? value : ""} onChange={e => changeValue(e.target.value === "" ? NaN : Number(e.target.value))}/></label>
    {inputProblem(holdings, value) === "value" && <p className={styles.problem}>{p("value")}</p>}
    <div className={styles.editorActions}><button type="button" className={styles.primary} disabled={busy !== null || !currentValid} onClick={() => run("analyze")}>{busy === "analyze" ? p("analyzing") : p("analyze")} <span aria-hidden="true">↗</span></button><button type="button" onClick={() => editor === "current" ? changeCurrent(exampleBefore) : changeProposed(exampleAfter)}>{p("example")}</button></div>
    <details className={styles.supportDetails}><summary>{ko ? "검색·분석 지원 범위" : "Search and analysis coverage"}</summary><p>{universe?.notice[ko ? "ko" : "en"] ?? (ko ? "종목 목록을 불러오는 중이거나 이용할 수 없습니다." : "The asset catalog is loading or unavailable.")}</p><p>{ko ? "검색 후보와 분석 승인 종목은 다릅니다. 한국 후보와 미지원 종목은 선택·분석할 수 없습니다." : "Discovery does not grant analysis access. Korean candidates and unsupported assets remain blocked."}</p></details>
   </aside>
   <div id="portfolio-results" className={styles.resultsPanel}>
    <div className={styles.workspaceTabs} role="tablist" aria-label={ko ? "포트폴리오 분석 작업" : "Portfolio analysis workspace"}>{tabs.map(tab => <button key={tab.id} id={`tab-${tab.id}`} role="tab" aria-selected={workspace === tab.id} aria-controls={`workspace-${tab.id}`} tabIndex={workspace === tab.id ? 0 : -1} onClick={() => tabTo(tab.id)} onKeyDown={e => {
     if (!["ArrowLeft","ArrowRight","Home","End"].includes(e.key)) return;
     e.preventDefault();
     const index = tabs.findIndex(t => t.id === workspace);
     const next = e.key === "Home" ? 0 : e.key === "End" ? tabs.length - 1 : (index + (e.key === "ArrowRight" ? 1 : -1) + tabs.length) % tabs.length;
     tabTo(tabs[next].id); document.getElementById(`tab-${tabs[next].id}`)?.focus();
    }}>{tab.label}</button>)}</div>
    {network && <ApiProblem error={network}/>}
    {error?.error.kind === "rejected" && <ApiProblem error={error.error}/>}
    {busy && <div className={styles.loadingState} role="status" aria-label={ko ? "위험 분석 결과를 불러오는 중" : "Loading risk analysis"}><span>{busy === "compare" ? p("comparing") : p("analyzing")}</span><div className={styles.skeleton}/><div className={styles.skeleton}/></div>}
    {tabs.filter(tab => tab.id !== workspace).map(tab => <section hidden key={tab.id} id={`workspace-${tab.id}`} role="tabpanel" aria-labelledby={`tab-${tab.id}`}/>)}
    <section id={`workspace-${workspace}`} role="tabpanel" aria-labelledby={`tab-${workspace}`} tabIndex={0} aria-busy={busy !== null} className={styles.workspaceContent}>
     {workspace === "diagnosis" && (analysis ? <HiddenRiskMap analysis={analysis}/> : !busy && <div className="panel empty-state"><span className="empty-symbol" aria-hidden="true">↗</span><h2>{ko ? "현재 입력의 위험을 확인하세요" : "Explore the risk in these holdings"}</h2><p>{p("reanalyze")}</p></div>)}
     {workspace === "scenarios" && (analysis ? <StressTest analysis={analysis} scenarios={scenarios}/> : !busy && <div className="panel empty-state"><h2>{ko ? "먼저 현재 포트폴리오를 분석하세요" : "Analyze the current portfolio first"}</h2><p>{p("reanalyze")}</p></div>)}
     {workspace === "whatif" && <>
      <div className="panel whatif-intro"><span className="section-index">COMPARE ON THE SAME BASIS</span><h2>{ko ? "비중을 바꾸고, 위험의 차이를 확인하세요." : "Change the weights. Understand the difference."}</h2><p>{p("whatifIntro")}</p><div className={styles.actions}><button type="button" onClick={() => {changeProposed(holdings);setEditor("proposed");}}>{p("fromCurrent")}</button><button type="button" onClick={() => {changeProposed(exampleAfter);setEditor("proposed");}}>{p("exampleShift")}</button><button type="button" className={styles.primary} disabled={busy !== null || !currentValid || !proposedValid} onClick={() => run("compare")}>{busy === "compare" ? p("comparing") : p("compare")} ↗</button></div></div>
      {comparison ? <><div className={styles.comparisonHero}><div><span>{p("current")} · {p("volatility")}</span><strong>{comparison.current.volatility.toFixed(1)}%</strong></div><span aria-hidden="true">→</span><div><span>{p("proposed")} · {p("volatility")}</span><strong>{comparison.proposed.volatility.toFixed(1)}%</strong></div></div><section className="panel"><WhatIfTable comparison={comparison}/></section></> : !busy && <div className="panel empty-state"><p>{ko ? "좌측에서 변경 포트폴리오를 편집한 뒤 비교하세요. 아직 계산된 변경 효과가 없습니다." : "Edit the changed portfolio on the left, then compare. No change has been calculated yet."}</p></div>}
     </>}
    </section>
    <details className={styles.marketContext}><summary>{p("marketTitle")} · {ko ? "시장 신호와 포트폴리오 위험 구분" : "Separate market signals from portfolio risk"}</summary><p>{p("riskScoreNote")}{marketAsOf && portfolioAsOf && marketAsOf !== portfolioAsOf && <> {p("dateGap").replace("{market}",marketAsOf).replace("{portfolio}",portfolioAsOf)}</>}</p><CountryCards only="us"/><Link className="text-link" href="/us">{p("checkMarket")} ↗</Link></details>
   </div>
  </div>
 </main>;
}
