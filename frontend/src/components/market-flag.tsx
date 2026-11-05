/** Decorative country identifiers; vector shapes avoid platform-dependent emoji fonts. */
export default function MarketFlag({country}:{country:"us"|"korea"}) {
 return <svg width="25" height="18" viewBox="0 0 30 21" aria-hidden="true" style={{display:"inline-block",verticalAlign:"middle",flexShrink:0,borderRadius:2}}>
  <rect width="30" height="21" fill="#f1f5fa"/>
  {country==="us"?<><g fill="#d95868">{Array.from({length:7},(_,i)=><rect key={i} y={i*3} width="30" height="1.6"/>)}</g><rect width="13" height="11.3" fill="#28507e"/><g fill="#f1f5fa">{Array.from({length:12},(_,i)=><circle key={i} cx={2+(i%4)*3} cy={2+Math.floor(i/4)*3.4} r=".65"/>)}</g></>:<><circle cx="15" cy="10.5" r="5" fill="#d34c61"/><path d="M10 10.5a2.5 2.5 0 0 0 5 0a2.5 2.5 0 0 1 5 0a5 5 0 0 1-10 0" fill="#326aa8"/><g stroke="#172335" strokeWidth="1"><path d="M4 4l3 3M3 5l3 3M2 6l3 3M23 14l3 3M24 13l3 3M25 12l3 3M23 4l-3 3M24 5l-3 3M25 6l-3 3M7 14l-3 3M8 15l-3 3M9 16l-3 3"/></g></>}
 </svg>;
}
