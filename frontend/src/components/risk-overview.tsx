"use client";
import Link from "next/link";
import { useDashboard } from "./dashboard-shell";
import { currentOperationalPoint } from "@/lib/operational-status";
import MarketFlag from "./market-flag";
import SignalAtlas from "./signal-atlas";
import styles from "./signal-atlas.module.css";

export default function RiskOverview() {
 const {language,global,monitor,operational}=useDashboard();
 const ko=language==="ko";
 return <div className={styles.overview}>
  <div className={styles.heading}><svg className={styles.ambientGlobe} viewBox="0 0 600 260" aria-hidden="true"><defs><clipPath id="ambient-globe-clip"><rect width="600" height="260"/></clipPath><radialGradient id="ambient-globe-light"><stop stopColor="#42bdf4" stopOpacity=".13"/><stop offset="1" stopColor="#07121e" stopOpacity="0"/></radialGradient></defs><g clipPath="url(#ambient-globe-clip)"><ellipse cx="360" cy="295" rx="290" ry="245" fill="url(#ambient-globe-light)" stroke="#69c8f5" strokeOpacity=".35"/>{Array.from({length:12},(_,i)=><ellipse key={`lat-${i}`} cx="360" cy={65+i*19} rx={Math.sqrt(Math.max(0,1-((65+i*19-295)/245)**2))*290} ry={9+i*3} fill="none" stroke="#69c8f5" strokeOpacity=".25" strokeDasharray="1 5"/>)}{Array.from({length:13},(_,i)=><ellipse key={`lon-${i}`} cx="360" cy="295" rx={20+i*22} ry="245" fill="none" stroke="#69c8f5" strokeOpacity=".22" strokeDasharray="1 6"/>)}</g></svg><div><span className={styles.eyebrow}>GLOBAL MARKET RISK MONITORING</span><h1>{ko?"글로벌 시장 위험 모니터링":"Global market risk monitoring"}</h1><p>{ko?"시장 스트레스 예측 점수와 현재 스트레스 수준, 위험 확산의 변화를 함께 확인합니다.":"Track predicted market stress, observed conditions and changes in market breadth."}</p></div><div className={styles.dataMode}><span>{ko?"자료 기준":"Data basis"}</span><a href="#latest-observations">{ko?"최신 관측 현황":"Latest observations"}</a><a href="#market-atlas">{ko?"과거 연구 자료":"Historical research"}</a></div></div>
  <section id="latest-observations" className={styles.latest} aria-label={ko?"최신 시장 위험 현황":"Latest market risk observations"}>
   {(["us","korea"] as const).map(country=>{
    const source=operational?.markets[country];
    const point=currentOperationalPoint(source);
    const status=point?(ko?"기준일 자료 확인":"Inputs verified for date"):source?.status==="BLOCKED"?(ko?"검증 보류":"Validation withheld"):source?.status==="DELAYED"?(ko?"자료 갱신 지연":"Delayed data"):(ko?"최신 자료 없음":"Current data unavailable");
    return <article key={country} className={styles.latestMarket} data-market={country}>
     <div className={styles.marketIdentity}><Link href={`/${country}`}><MarketFlag country={country}/>{country==="us"?(ko?"미국 시장":"United States"):(ko?"한국 시장":"South Korea")}<span aria-hidden="true">↗</span></Link><span className={point?styles.verifiedStatus:styles.pendingStatus}>{status}</span></div>
     <div className={styles.latestMetric}><span>{ko?"시장 스트레스 예측 점수":"Risk Score"}<small>{ko?"향후 10거래일":"Next 10 trading days"}</small></span><strong data-value="risk" className={!point?styles.noValue:undefined}>{point?.risk==null?"N/A":`${(point.risk*100).toFixed(1)}%`}</strong></div>
     <div className={styles.latestMetric}><span>{ko?"시장 스트레스 지수 (MSI)":"Market Stress Index (MSI)"}<small>{ko?"관측 스트레스":"Observed stress"}</small></span><strong data-value="msi" className={!point?styles.noValue:undefined}>{point?.msi?.toFixed(3)??"N/A"}</strong></div>
     <div className={styles.latestDates}><span>{ko?"점수 관측일":"Score observed"}<time>{point?.date??"N/A"}</time></span><span>{ko?"수집 기준일":"Due observation"}<time>{source?.expectedDate??"N/A"}</time></span></div>
     {!point && <p className={styles.srOnly}>{ko?"최신 위험 점수 없음 · 과거 점수로 대체하지 않습니다.":"No current score. Historical values are not substituted."}</p>}
    </article>;
   })}
  </section>
  <div className={styles.latestNote}><span>{ko?"최신 현황과 아래의 과거 연구 자료는 기준일이 다릅니다.":"Current observations and the historical research below have separate dates."}</span><details><summary>{ko?"지표와 자료 기준 안내":"About these indicators"}</summary><p>{ko?"예측 위험 점수(Risk Score)는 향후 10거래일 내 시장 스트레스 위험을 나타내는 예측 지표입니다. 실제 발생 확률과 동일하게 해석할 수 없습니다. MSI는 해당 관측일의 시장 스트레스 수준입니다. 최신 현황은 현재 보유한 운영 자료를 기준으로 하며 실시간 값이 아닙니다.":"Risk Score is a predictive signal for stress within the next 10 trading days, not a calibrated occurrence probability. MSI measures stress on the observation date. Latest refers to available operational snapshots, not live data."}</p></details></div>
  {global && (global.us.length||global.korea.length)?<SignalAtlas global={global} monitor={monitor}/>:<section className={styles.empty}><h2>{ko?"시장 자료를 불러올 수 없습니다":"Market data is unavailable"}</h2><p>{ko?"과거 연구 자료가 없습니다. 최신 현황은 위의 자료 상태를 확인하세요.":"Historical research is unavailable. Refer to the current data status above."}</p></section>}
 </div>;
}
