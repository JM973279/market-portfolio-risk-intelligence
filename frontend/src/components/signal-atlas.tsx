"use client";
import { useEffect, useId, useMemo, useRef, useState, type PointerEvent } from "react";
import Link from "next/link";
import { useDashboard } from "./dashboard-shell";
import type { GlobalData, MarketPoint, MonitorData } from "@/lib/dashboard-types";
import { chartRanges, timestamp, type ChartRange } from "@/lib/chart-data";
import { finiteValue, metricDomain, observationAt, signalPath, type RiskMetric } from "@/lib/risk-explorer";
import { atlasDates, atlasRange, breadthColor, breadthSignals, breadthValue, clampAtlasWindow, nearestDateIndex, type AtlasWindow } from "@/lib/atlas-data";
import styles from "./signal-atlas.module.css";
import MarketFlag from "./market-flag";

const valueText=(value:number|null|undefined,percent=false)=>finiteValue(value)===null?"N/A":percent?`${(value!*100).toFixed(1)}%`:value!.toFixed(3);
const stateNames:Record<string,[string,string]>={
 "NORMAL":["경고 조건 미충족","Warning conditions not met"],
 "ALIGNED RISK":["위험 신호 일치","Aligned risk signals"],
 "MODEL-LED WARNING":["예측 지표 경고","Predictive warning"],
 "SIGNAL DIVERGENCE":["신호 괴리","Signal divergence"],
 "OBSERVED MSI STRESS":["MSI 스트레스 관측","Observed MSI stress"],
 "UNKNOWN / INSUFFICIENT DATA":["판정 불가 · 자료 부족","Insufficient data for classification"],
};

export default function SignalAtlas({global,monitor}:{global:GlobalData;monitor:MonitorData|null}) {
 const {language}=useDashboard();
 const ko=language==="ko";
 const dates=useMemo(()=>atlasDates(global,monitor),[global,monitor]);
 const [window,setWindow]=useState<AtlasWindow>(()=>atlasRange(dates,"6M"));
 const [range,setRange]=useState<ChartRange|"CUSTOM">("6M");
 const [selected,setSelected]=useState(()=>[...global.korea].reverse().find(p=>finiteValue(p.risk)!==null&&finiteValue(p.msi)!==null&&finiteValue(observationAt(global.us,p.date)?.risk)!==null)?.date??dates.at(-1)??"");
 const [hovered,setHovered]=useState<string|null>(null);
 const [ready,setReady]=useState(false);
 const [view,setView]=useState<"both"|RiskMetric>("both");
 const [activeSignal,setActiveSignal]=useState<string>(breadthSignals[0].key);
 const dragStart=useRef<number|null>(null);
 const dragWindowSize=useRef(0);
 const evidence=useRef<HTMLDetailsElement>(null);
 const id=useId().replaceAll(":","");
 useEffect(()=>{
  const media=windowMatch();
  const timer=setTimeout(()=>{
   let restored=false;
   try {
    const saved=JSON.parse(sessionStorage.getItem("mpri-atlas-lens")??"null");
    if(saved?.version===2 && dates.includes(saved.from) && dates.includes(saved.to) && saved.from<saved.to) {
     setWindow(clampAtlasWindow(dates,dates.indexOf(saved.from),dates.indexOf(saved.to)));
     setSelected(typeof saved.day==="string" && saved.day>=saved.from && saved.day<=saved.to?saved.day:saved.to);
     setRange(chartRanges.includes(saved.range)?saved.range:"CUSTOM");
     if(["both","risk","msi"].includes(saved.view))setView(saved.view);
     restored=true;
    }
   }catch{/* Preferences are optional. */}
   if(!restored){const initial=media.matches?"3M":"6M";setWindow(atlasRange(dates,initial));setRange(initial);}
   setReady(true);
  },0);
  return()=>clearTimeout(timer);
 },[dates]);
 useEffect(()=>{
  if(!ready)return;
  try{sessionStorage.setItem("mpri-atlas-lens",JSON.stringify({version:2,from:dates[window[0]],to:dates[window[1]],day:selected,range,view}));}catch{/* Optional storage. */}
 },[ready,dates,window,selected,range,view]);
 const from=dates[window[0]]??global.asOf??"",to=dates[window[1]]??global.asOf??"";
 const shownDates=useMemo(()=>dates.slice(window[0],window[1]+1),[dates,window]);
 const day=hovered??selected;
 const shownUS=useMemo(()=>global.us.filter(p=>p.date>=from&&p.date<=to),[global.us,from,to]);
 const shownKR=useMemo(()=>global.korea.filter(p=>p.date>=from&&p.date<=to),[global.korea,from,to]);
 const breadthRows=useMemo(()=>monitor?.history.filter(r=>r.Date>=from&&r.Date<=to)??[],[monitor,from,to]);
 const byDate=useMemo(()=>new Map(monitor?.history.map(r=>[r.Date,r])??[]),[monitor]);
 const row=byDate.get(day);
 const us=observationAt(global.us,day),kr=observationAt(global.korea,day);
 const state=stateNames[row?.state??"UNKNOWN / INSUFFICIENT DATA"];
 const span=Math.max(1,timestamp(to)-timestamp(from));
 const x=(date:string)=>(timestamp(date)-timestamp(from))/span*1000;
 const fullStart=dates[0]??from,fullEnd=dates.at(-1)??to;
 const fullSpan=Math.max(1,timestamp(fullEnd)-timestamp(fullStart));
 const fullX=(date:string)=>(timestamp(date)-timestamp(fullStart))/fullSpan*1000;
 const leftPercent=fullX(from)/10,rightPercent=fullX(to)/10;
 const selectedIndex=nearestDateIndex(shownDates,selected);
 const signal=breadthSignals.find(s=>s.key===activeSignal)??breadthSignals[0];
 const percentile=breadthValue(row,`${signal.key}_pct`),share=breadthValue(row,signal.key);
 const setInterval=(next:AtlasWindow,nextRange:ChartRange|"CUSTOM"="CUSTOM")=>{
  const valid=clampAtlasWindow(dates,...next);setWindow(valid);setRange(nextRange);setHovered(null);
  if(selected<dates[valid[0]]||selected>dates[valid[1]])setSelected(dates[valid[1]]);
 };
 const pickDay=(event:{clientX:number;currentTarget:SVGSVGElement})=>{
  const box=event.currentTarget.getBoundingClientRect();
  const time=timestamp(from)+Math.max(0,Math.min(1,(event.clientX-box.left)/box.width))*span;
  return shownDates[nearestDateIndex(shownDates,new Date(time).toISOString().slice(0,10))]??from;
 };
 const brushIndex=(event:PointerEvent<SVGSVGElement>)=>{
  const box=event.currentTarget.getBoundingClientRect();
  const time=timestamp(fullStart)+Math.max(0,Math.min(1,(event.clientX-box.left)/box.width))*fullSpan;
  return nearestDateIndex(dates,new Date(time).toISOString().slice(0,10));
 };
 const startBrush=(event:PointerEvent<SVGSVGElement>)=>{
  dragStart.current=brushIndex(event);
  dragWindowSize.current=window[1]-window[0];
  event.currentTarget.setPointerCapture(event.pointerId);
 };
 const moveBrush=(event:PointerEvent<SVGSVGElement>)=>{
  const index=brushIndex(event);
  if(dragStart.current!==null && index!==dragStart.current)setInterval([dragStart.current,index]);
 };
 const finishBrush=(event:PointerEvent<SVGSVGElement>)=>{
  if(dragStart.current===null)return;
  const index=brushIndex(event);
  if(index===dragStart.current){
   const length=dragWindowSize.current;
   const first=Math.max(0,Math.min(dates.length-1-length,index-Math.floor(length/2)));
   setInterval([first,first+length]);
  }else setInterval([dragStart.current,index]);
  dragStart.current=null;
  event.currentTarget.releasePointerCapture(event.pointerId);
 };
 const zoom=(factor:number)=>{
  const center=nearestDateIndex(dates,selected);
  const length=Math.max(2,Math.round((window[1]-window[0]+1)*factor));
  let first=Math.max(0,center-Math.floor(length/2));
  const last=Math.min(dates.length-1,first+length-1);first=Math.max(0,last-length+1);
  setInterval([first,last]);
 };
 if(!dates.length)return <div className={styles.empty}>{ko?"조회할 과거 자료가 없습니다.":"No historical observations available."}</div>;
 const lanes:{country:"us"|"korea";metric:RiskMetric;points:MarketPoint[]}[]=[
  {country:"us",metric:"risk",points:shownUS},{country:"us",metric:"msi",points:shownUS},
  {country:"korea",metric:"risk",points:shownKR},{country:"korea",metric:"msi",points:shownKR},
 ];
 return <section id="market-atlas" className={styles.atlas} aria-label={ko?"시장 위험 지도와 기간별 분석":"Signal Atlas and temporal analysis"}>
  <div className={styles.atlasHeading}><div><span className={styles.sectionNumber}>SIGNAL ATLAS</span><h2>{ko?"시장 위험 지도":"Market risk atlas"}</h2></div><span className={styles.researchScope}>{ko?"과거 연구 자료":"Historical research"}<time>{fullStart} — {fullEnd}</time></span></div>
  <div className={styles.mapMain}>
  <div className={styles.controls}>
   <div className={styles.periods} role="group" aria-label={ko?"조회 기간":"Viewing period"}>{chartRanges.map(r=><button key={r} aria-pressed={range===r} onClick={()=>setInterval(atlasRange(dates,r),r)}>{ko?({"1M":"1개월","3M":"3개월","6M":"6개월","1Y":"1년","ALL":"전체"}[r]):r}</button>)}</div>
   <div className={styles.detailControls}><select aria-label={ko?"표시 지표":"Visible indicators"} value={view} onChange={e=>setView(e.target.value as typeof view)}><option value="both">{ko?"예측 점수 + MSI":"Risk Score + MSI"}</option><option value="risk">{ko?"예측 위험 점수":"Risk Score"}</option><option value="msi">MSI</option></select><div className={styles.zoomButtons}><button aria-label={ko?"선택일 중심으로 구간 확대":"Zoom in around selected date"} onClick={()=>zoom(.5)} disabled={window[1]-window[0]<3}>＋</button><button aria-label={ko?"조회 구간 축소":"Zoom out"} onClick={()=>zoom(2)} disabled={window[0]===0&&window[1]===dates.length-1}>−</button></div></div>
  </div>
  <div className={styles.tracks}>
   <svg className={styles.svgDefinitions} aria-hidden="true"><defs><pattern id={`${id}-missing`} width="7" height="7" patternUnits="userSpaceOnUse"><path d="M0 7L7 0" stroke="#52677a" strokeWidth=".7" opacity=".5"/></pattern></defs></svg>
   {lanes.filter(l=>view==="both"||l.metric===view).map(lane=>{
    const [min,max]=metricDomain(lane.points,lane.metric),y=(v:number)=>68-(v-min)/(max-min)*58;
    const color=lane.country==="us"?"#69C8F5":"#C9D5E2";
    const point=lane.country==="us"?observationAt(shownUS,day):observationAt(shownKR,day);
    const current=point?.[lane.metric];
    const pointsByDate=new Map(lane.points.map(p=>[p.date,p]));
    return <div className={styles.trackRow} key={`${lane.country}-${lane.metric}`} data-series={`${lane.country}-${lane.metric}`}>
     <div className={styles.trackLabel}><span style={{color}}>{lane.country==="us"?(ko?"미국":"US"):(ko?"한국":"Korea")}</span><b>{lane.metric==="risk"?(ko?"예측 위험 점수":"Risk Score"):"MSI"}</b><small>{lane.metric==="risk"?(ko?"과거 검증 · 0–100%":"Historical OOS · 0–100%"): `${min.toFixed(1)} — ${max.toFixed(1)}`}</small></div>
     <svg className={styles.trackGraphic} viewBox="0 0 1000 78" preserveAspectRatio="none" role="img" aria-label={`${lane.country==="us"?(ko?"미국":"US"):(ko?"한국":"Korea")} ${lane.metric==="risk"?(ko?"예측 위험 점수":"Risk Score"):"MSI"} ${from} — ${to}`} onPointerMove={e=>setHovered(pickDay(e))} onPointerLeave={()=>setHovered(null)} onClick={e=>{setSelected(pickDay(e));setHovered(null);}}>
      <defs><clipPath id={`${id}-${lane.country}-${lane.metric}`}><rect width="1000" height="78"/></clipPath></defs>
      {[0,.5,1].map(n=><line key={n} x1="0" x2="1000" y1={y(min+n*(max-min))} y2={y(min+n*(max-min))} className={styles.gridline}/>)}
      <g clipPath={`url(#${id}-${lane.country}-${lane.metric})`}>
       {lane.metric==="risk"?null:<path d={signalPath(lane.points,"threshold",x,y)} fill="none" className={styles.threshold}/>}
       {lane.metric==="risk" ? Array.from({length:Math.floor(span/86400000)+1},(_,index)=>{
        const date=new Date(timestamp(from)+index*86400000).toISOString().slice(0,10);
        const value=finiteValue(pointsByDate.get(date)?.risk);
        const width=Math.max(.1,Math.min(1000,86400000/span*1000));
        return <rect key={date} x={x(date)} y="12" width={width} height="54" fill={value===null?`url(#${id}-missing)`: `rgba(105,200,245,${.12+Math.max(0,Math.min(1,value))*.88})`}><title>{`${date}: ${valueText(value,true)}`}</title></rect>;
       }):<path d={signalPath(lane.points,lane.metric,x,y)} stroke={color} strokeWidth="2.2" fill="none" vectorEffect="non-scaling-stroke" strokeLinejoin="round"/>}
       <line x1={x(day)} x2={x(day)} y1="0" y2="78" className={styles.cursor}/>
       {finiteValue(current)!==null&&<circle cx={x(day)} cy={y(current!)} r="3" fill={color} vectorEffect="non-scaling-stroke"/>}
      </g>
     </svg><div className={styles.trackValue} style={{color}}>{valueText(current,lane.metric==="risk")}</div>
    </div>;
   })}
  </div>
  <div className={styles.chartDates}><time>{from}</time><span>{shownDates[Math.floor(shownDates.length/2)]}</span><time>{to}</time></div>
  <div className={styles.matrixHeading}><h3>{ko?"한국 시장 확산도":"Korea market breadth"}</h3><div className={styles.matrixLegend}><span>{ko?"과거 기준 백분위":"Past-only percentile"}</span><i className={styles.lowKey}/><span>{ko?"낮음":"Low"}</span><i className={styles.highKey}/><span>≥90%</span><span className={styles.missingKey}>{ko?"빈칸: 자료 없음 · 사선: 예측 점수 없음":"Blank: no breadth data · hatching: no Risk Score"}</span></div></div>
  <div className={styles.matrix} aria-label={ko?"한국 확산도 지표 6개의 관측일별 백분위":"Stored daily percentiles of six Korea breadth indicators"}>
   {breadthSignals.map(s=>{
    const value=breadthValue(row,`${s.key}_pct`);
    const cellWidth=Math.max(.08,Math.min(40,86400000/span*1000));
    return <div className={styles.matrixRow} key={s.key}>
     <button className={styles.signalLabel} aria-pressed={activeSignal===s.key} onClick={()=>setActiveSignal(s.key)}>{ko?s.ko:s.en}</button>
     <svg viewBox="0 0 1000 26" preserveAspectRatio="none" role="img" aria-label={`${ko?s.ko:s.en} · ${ko?"과거 기준 백분위":"past-only percentile"}`} onPointerMove={e=>{setHovered(pickDay(e));setActiveSignal(s.key);}} onPointerLeave={()=>setHovered(null)} onClick={e=>{setSelected(pickDay(e));setActiveSignal(s.key);setHovered(null);}}>
      {breadthRows.map(r=><rect key={r.Date} x={Math.min(1000-cellWidth,Math.max(0,x(r.Date)-cellWidth/2))} y="1" width={cellWidth} height="24" fill={breadthColor(breadthValue(r,`${s.key}_pct`))}/>)}
      <line x1={x(day)} x2={x(day)} y1="0" y2="26" className={styles.cursor}/>
     </svg><span className={styles.percentileValue}>{value===null?"N/A":`${(value*100).toFixed(1)}%`}</span>
    </div>;
   })}
  </div>
  <details className={styles.persistenceDetails}><summary>{ko?"지속 악화 판정과 색상 기준":"Persistence classification and color scale"}</summary>  <div className={`${styles.matrixRow} ${styles.persistenceRow}`}>
   <span className={styles.persistenceLabel}>{ko?"지속 악화 조건":"Persistent deterioration"}<small>{ko?"저장된 판정":"Stored classification"}</small></span>
   <svg viewBox="0 0 1000 24" preserveAspectRatio="none" role="img" aria-label={ko?"저장된 확산도 지속 악화 조건 충족 여부":"Stored breadth persistence classifications"} onPointerMove={e=>setHovered(pickDay(e))} onPointerLeave={()=>setHovered(null)} onClick={e=>{setSelected(pickDay(e));setHovered(null);}}>
    {breadthRows.map(r=>{const width=Math.max(.08,Math.min(40,86400000/span*1000));return <rect key={r.Date} x={Math.min(1000-width,Math.max(0,x(r.Date)-width/2))} y="7" width={width} height="10" fill={r.persistent==null?"transparent":r.persistent===1?"#F3B54A":"#203449"}/>;})}
    <line x1={x(day)} x2={x(day)} y1="0" y2="24" className={styles.cursor}/>
   </svg><span className={styles.percentileValue}>{row?.persistent==null?(ko?"자료 없음":"N/A"):row.persistent===1?(ko?"충족":"Met"):(ko?"미충족":"Not met")}</span>
  </div>
  <p className={styles.matrixExplanation}>{ko?"6개 지표의 황색 칸은 과거 기준 백분위 90% 이상입니다. 아래 지속 악화 행은 저장된 판정이며 새로운 종합 위험 점수가 아닙니다.":"Amber cells in the six indicator rows mark stored percentiles ≥90%. The persistence row uses stored classifications, not a new composite risk score."}</p>
</details>
  <details className={styles.timelineOptions}><summary>{ko?"전체 기간 탐색 및 구간 조정":"Explore full history and adjust interval"}</summary>  <div className={styles.lens}>
   <div className={styles.lensHeading}><span>{ko?"전체 기간에서 조회 구간 선택":"Select an interval from the full history"}</span><span>{ko?"드래그로 선택 · 아래 조절자로도 변경 가능":"Drag to select · or use the controls below"}</span></div>
   <div className={styles.navigator}>
    <svg viewBox="0 0 1000 62" preserveAspectRatio="none" role="img" aria-label={ko?"전체 기간의 미국·한국 예측 위험 점수. 드래그로 조회 기간 선택.":"Full US and Korea Risk Score history. Drag to select a viewing interval."} onPointerDown={startBrush} onPointerMove={moveBrush} onPointerUp={finishBrush} onPointerCancel={()=>{dragStart.current=null;}}>
     <path d={signalPath(global.us,"risk",fullX,v=>27-v*24)} fill="none" stroke="#69C8F5" strokeWidth="1" vectorEffect="non-scaling-stroke"/>
     <path d={signalPath(global.korea,"risk",fullX,v=>60-v*24)} fill="none" stroke="#C9D5E2" strokeWidth="1" vectorEffect="non-scaling-stroke"/>
    </svg><div className={styles.selectionMask} style={{left:`${leftPercent}%`,width:`${Math.max(.3,rightPercent-leftPercent)}%`}}><span/><span/></div>
   </div>
   <div className={styles.fullDates}><time>{fullStart}</time><span>{ko?"미국 · 한국 예측 위험 점수 / 개별 축":"US · Korea Risk Score / separate scales"}</span><time>{fullEnd}</time></div>
   <div className={styles.windowHandles}><label>{ko?"시작":"From"}<input type="range" aria-label={ko?"조회 시작일 조절":"Adjust interval start"} min={0} max={Math.max(0,dates.length-2)} value={window[0]} aria-valuetext={from} onChange={e=>setInterval([Math.min(Number(e.target.value),window[1]-1),window[1]])}/><time>{from}</time></label><label>{ko?"종료":"To"}<input type="range" aria-label={ko?"조회 종료일 조절":"Adjust interval end"} min={1} max={Math.max(1,dates.length-1)} value={window[1]} aria-valuetext={to} onChange={e=>setInterval([window[0],Math.max(window[0]+1,Number(e.target.value))])}/><time>{to}</time></label></div>
  </div>
</details>

  </div>
  <details ref={evidence} className={styles.evidence} open>
   <summary><span>{ko?"선택일 상세 정보":"Selected date details"}<time>{day}</time></span><span className={styles.evidenceState}>{ko?"한국 연구 판정 · ":"Korea research status · "}{state?.[ko?0:1]??(ko?"자료 없음":"No data")}</span></summary>
  <div className={styles.dateInspector}>
   <div className={styles.selectedDate}><span>{ko?"날짜 선택":"Choose date"}</span><input type="date" aria-label={ko?"관측일 직접 선택":"Choose observation date"} min={from} max={to} value={selected} onChange={e=>{if(e.target.value>=from&&e.target.value<=to){setSelected(e.target.value);setHovered(null);}}}/></div>
   <div className={styles.observationStepper}><button aria-label={ko?"이전 관측일":"Previous observation"} disabled={selectedIndex===0} onClick={()=>{setSelected(shownDates[Math.max(0,selectedIndex-1)]);setHovered(null);}}>←</button><input type="range" aria-label={ko?"조회 관측일 이동":"Move through observations"} min={0} max={Math.max(0,shownDates.length-1)} value={selectedIndex} aria-valuetext={selected} onChange={e=>{setSelected(shownDates[Number(e.target.value)]);setHovered(null);}}/><button aria-label={ko?"다음 관측일":"Next observation"} disabled={selectedIndex>=shownDates.length-1} onClick={()=>{setSelected(shownDates[Math.min(shownDates.length-1,selectedIndex+1)]);setHovered(null);}}>→</button></div>
   <button className={styles.evidenceButton} onClick={()=>{if(evidence.current){evidence.current.open=true;evidence.current.scrollIntoView({block:"start",behavior:globalThis.matchMedia("(prefers-reduced-motion:reduce)").matches?"instant":"smooth"});}}}>{ko?"관측 근거 확인":"Inspect evidence"}<span aria-hidden="true">↘</span></button>
  </div>
   <div className={styles.sidebarMarkets}>{([{key:"korea",point:kr,flag:"🇰🇷",name:ko?"한국 시장":"Korea"},{key:"us",point:us,flag:"🇺🇸",name:ko?"미국 시장":"US"}]).map(m=><div key={m.key}><h3><MarketFlag country={m.key as "us"|"korea"}/> {m.name}</h3><dl><div><dt>{ko?"예측 점수 (Risk Score)":"Risk Score"}</dt><dd>{valueText(m.point?.risk,true)}</dd></div><div><dt>{ko?"MSI (관측 스트레스)":"MSI (observed stress)"}</dt><dd>{valueText(m.point?.msi)}</dd></div></dl>{!m.point&&<p>{ko?"선택한 날짜의 연구 관측값이 없습니다.":"No research observation on this date."}</p>}</div>)}</div>
   <p className={styles.factorAvailability}>{ko?"위험 요인 해석(SHAP)은 현재 자료에 포함되지 않습니다.":"SHAP risk-factor attribution is not included in this dataset."}</p>
   <div className={styles.sidebarBreadth}><h3>{ko?"한국 시장 확산도":"Korea market breadth"}<small>{ko?"과거 기준 백분위":"Past-only percentile"}</small></h3>{breadthSignals.map(s=>{const value=breadthValue(row,`${s.key}_pct`);return <div key={s.key}><span>{ko?s.ko:s.en}</span><div className={styles.barTrack}><i style={{width:`${(value??0)*100}%`,background:breadthColor(value)}}/></div><b>{valueText(value,true)}</b></div>;})}</div>
   <details className={styles.additionalEvidence}><summary>{ko?"판정 근거와 분석 한계":"Classification and limitations"}</summary><div className={styles.evidenceGrid}>
    <div><h3>{ko?"같은 날짜의 실제 관측값":"Exact-date observations"}</h3><dl><div><dt>{ko?"미국 예측 점수 / MSI":"US Risk Score / MSI"}</dt><dd>{valueText(us?.risk,true)} / {valueText(us?.msi)}</dd></div><div><dt>{ko?"한국 예측 점수 / MSI":"Korea Risk Score / MSI"}</dt><dd>{valueText(kr?.risk,true)} / {valueText(kr?.msi)}</dd></div><div><dt>{ko?"MSI 공식 임계값 · 미국 / 한국":"MSI threshold · US / Korea"}</dt><dd>{valueText(us?.threshold)} / {valueText(kr?.threshold)}</dd></div></dl></div>
    <div><h3>{ko?signal.ko:signal.en}</h3><dl><div><dt>{ko?"해당 종목 비율":"Stock share"}</dt><dd>{valueText(share,true)}</dd></div><div><dt>{ko?"과거 기준 백분위":"Past-only percentile"}</dt><dd>{valueText(percentile,true)}</dd></div><div><dt>{ko?"극단 수준 지표 수 / 전체":"Extreme indicators / total"}</dt><dd>{row?.extreme_count==null?"N/A":`${row.extreme_count.toFixed(0)} / 6`}</dd></div></dl></div>
    <div><h3>{ko?"자료와 판정 범위":"Data and classification scope"}</h3><p>{row?.persistent==null?(ko?"지속 여부를 판단할 자료가 부족합니다.":"Persistence data is insufficient."):row.persistent===1?(ko?"지속 악화 조건을 충족했습니다.":"Persistent deterioration conditions are met."):(ko?"지속 악화 조건을 충족하지 않았습니다.":"Persistent deterioration conditions are not met.")}</p><p>{ko?"자료가 없는 날짜는 이전 값으로 채우지 않습니다. 예측 점수는 과거 검증 결과이며 최신 현황과 구분합니다.":"Missing observations are never filled. Historical predictive scores are separate from current observations."}</p><Link href="/methodology">{ko?"판정 기준과 분석 한계":"Methodology and limitations"} ↗</Link></div>
   </div>
   </details><details className={styles.provenance}><summary>{ko?"자료 출처와 제공 범위":"Sources and availability"}</summary><p>{ko?`연구 자료 기준일 ${global.asOf??"N/A"}. 최신 운영 현황을 이 시계열에 이어 붙이지 않습니다. 현재 자료에는 SHAP 분석 결과가 없습니다.`:`Research as of ${global.asOf??"N/A"}. Operational points are not appended to these series. No SHAP export is connected.`}</p><ul>{Object.entries(global.sources).map(([key,source])=><li key={key}><b>{key}</b><span>{source.latest??"N/A"}</span><code>{source.path}</code></li>)}</ul><Link href="/sources">{ko?"전체 데이터 정보":"All data sources"} ↗</Link></details>
  </details>
  <p className={styles.interpretation}>{ko?"양국의 모델은 독립적이므로 점수 차이를 위험 순위로 해석할 수 없습니다. MSI는 시장별 개별 축을 사용합니다. 예측 점수 색상은 0–100%에 대응하며, MSI 점선은 해당 관측일의 공식 임계값입니다. 사선은 예측 점수가 없는 날짜입니다.":"Models are independent: score differences are not a market risk ranking. MSI uses separate market scales. Risk Score colors represent 0–100%; MSI dashed lines are stored date-specific thresholds. Hatching marks missing Risk Scores."}</p>
  <div className={styles.relatedLinks}><span>{ko?"관련 분석":"Related analysis"}</span><Link href="/breadth">{ko?"시장 확산도":"Market breadth"} ↗</Link><Link href="/validation">{ko?"과거 검증":"Validation"} ↗</Link><Link href="/cases">{ko?"사례 분석":"Case studies"} ↗</Link><Link href="/portfolio">{ko?"포트폴리오 분석":"Portfolio analysis"} ↗</Link></div>
  <span className={styles.srOnly} aria-live="polite">{ko?"조회 관측일":"Observation"} {day}</span>
 </section>;
}

function windowMatch(){return globalThis.matchMedia("(max-width:760px)");}
