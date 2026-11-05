"use client";
import { useEffect, useRef } from "react";
import Link from "next/link";
import type { Language } from "@/lib/monitor-copy";
import styles from "./signal-atlas.module.css";

export default function HomeNavigation({language,onLanguage}:{language:Language;onLanguage:(language:Language)=>void}) {
 const ko=language==="ko";
 const menu=useRef<HTMLDetailsElement>(null);
 useEffect(()=>{
  const close=(event:KeyboardEvent)=>{if(event.key==="Escape"&&menu.current?.open){menu.current.open=false;menu.current.querySelector("summary")?.focus();}};
  document.addEventListener("keydown",close);return()=>document.removeEventListener("keydown",close);
 },[]);
 return <header className={styles.navigation}>
  <Link href="/" className={styles.brand} aria-label={ko?"M/PRI 시장 현황":"M/PRI market overview"}>M<span>/</span>PRI<span className={styles.brandCaption}>Market & Portfolio Risk Intelligence</span></Link>
  <nav className={styles.primaryNav} aria-label={ko?"주요 메뉴":"Primary navigation"}>
   <Link href="/" aria-current="page">{ko?"시장 현황":"Overview"}</Link><Link href="/us">{ko?"미국 시장":"US market"}</Link><Link href="/korea">{ko?"한국 시장":"Korea market"}</Link><Link href="/portfolio">{ko?"포트폴리오":"Portfolio"}</Link>
  <Link href="/validation">{ko?"과거 검증":"Validation"}</Link><Link href="/cases">{ko?"사례 분석":"Cases"}</Link><Link href="/sources">{ko?"데이터":"Data"}</Link><Link href="/methodology">{ko?"연구 방법론":"Methodology"}</Link></nav>
  <div className={styles.navActions}><details ref={menu} className={styles.moreMenu}><summary>{ko?"전체 메뉴":"All pages"}<span aria-hidden="true">＋</span></summary><nav aria-label={ko?"전체 서비스 메뉴":"All service pages"}>{[["/breadth","시장 확산도","Market breadth"],["/validation","과거 검증","Validation"],["/cases","사례 분석","Case studies"],["/sources","데이터 정보","Data sources"],["/methodology","연구 방법론","Methodology"]].map(([href,kr,en])=><Link key={href} href={href}>{ko?kr:en}<span aria-hidden="true">↗</span></Link>)}</nav></details><div className={styles.languages} role="group" aria-label="언어 / Language"><button aria-pressed={ko} onClick={()=>onLanguage("ko")} lang="ko">한국어</button><button aria-pressed={!ko} onClick={()=>onLanguage("en")} lang="en">EN</button></div></div>
 </header>;
}
