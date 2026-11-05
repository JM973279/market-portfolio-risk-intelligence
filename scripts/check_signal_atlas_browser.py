"""Local Chromium checks for the Signal Atlas homepage only.

Uses the installed browser and websockets. MPRI_ATLAS_URL defaults to local 3118.
Screenshots/reports remain in /tmp; no source or market-data files are changed.
"""
import asyncio
import base64
import json
import os
from pathlib import Path
import subprocess
import tempfile
import urllib.parse
import urllib.request

import websockets

ROOT=Path(__file__).resolve().parents[1]
URL=os.environ.get('MPRI_ATLAS_URL','http://127.0.0.1:3118')
OUT=Path(os.environ.get('MPRI_ATLAS_OUTPUT','/tmp/mpri-signal-atlas'))


async def main():
    if urllib.parse.urlsplit(URL).hostname not in {'127.0.0.1','localhost'}:
        raise ValueError('Local browser checks only')
    OUT.mkdir(parents=True,exist_ok=True)
    env=dict(os.environ)
    if os.environ.get('MPRI_BROWSER_LIBS'): env['LD_LIBRARY_PATH']=os.environ['MPRI_BROWSER_LIBS']
    data=json.loads((ROOT/'frontend/public/data/global-markets.json').read_text())
    monitor=json.loads((ROOT/'frontend/public/data/korea-monitor.json').read_text())
    checks,exceptions,console_errors=[],[],[]
    with tempfile.TemporaryDirectory(prefix='mpri-atlas-chrome-') as profile,(OUT/'chromium.log').open('w') as log:
        process=subprocess.Popen([os.environ['MPRI_CHROMIUM'],'--headless','--no-sandbox','--disable-dev-shm-usage',
            '--disable-background-networking','--no-first-run','--disable-sync','--remote-debugging-port=0',
            f'--user-data-dir={profile}','about:blank'],env=env,stdout=log,stderr=log)
        try:
            active=Path(profile)/'DevToolsActivePort'
            for _ in range(200):
                if active.exists(): break
                await asyncio.sleep(.1)
            port=active.read_text().splitlines()[0]
            targets=json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list',timeout=10))
            async with websockets.connect(next(t['webSocketDebuggerUrl'] for t in targets if t['type']=='page'),max_size=40_000_000) as ws:
                serial=0
                async def command(method,params=None):
                    nonlocal serial
                    serial+=1;ident=serial
                    await ws.send(json.dumps({'id':ident,'method':method,'params':params or {}}))
                    while True:
                        response=json.loads(await asyncio.wait_for(ws.recv(),30))
                        if response.get('method')=='Runtime.exceptionThrown':exceptions.append(response['params']['exceptionDetails'])
                        if response.get('method')=='Runtime.consoleAPICalled' and response['params']['type']=='error':console_errors.append(response['params']['args'])
                        if response.get('id')==ident:
                            if 'error' in response:raise AssertionError(response)
                            return response.get('result',{})
                async def evaluate(js):
                    result=await command('Runtime.evaluate',{'expression':js,'returnByValue':True,'awaitPromise':True})
                    if 'exceptionDetails' in result:raise AssertionError(result['exceptionDetails'])
                    return result['result'].get('value')
                async def wait(js):
                    for _ in range(150):
                        if await evaluate(js):return
                        await asyncio.sleep(.1)
                    raise AssertionError('Timed out: '+js)
                async def click(text):
                    await evaluate(f"""(()=>{{const b=[...document.querySelectorAll('button')].find(el=>el.textContent.trim()==={json.dumps(text)});if(!b||b.disabled)throw Error('Button unavailable: '+{json.dumps(text)});b.click();}})()""")
                async def set_input(selector,value):
                    await evaluate(f"""(()=>{{const el=document.querySelector({json.dumps(selector)});if(!el)throw Error('Input absent');el.focus();Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,{json.dumps(str(value))});el.dispatchEvent(new Event('input',{{bubbles:true}}));el.dispatchEvent(new Event('change',{{bubbles:true}}));}})()""")
                async def screenshot(name,full=False):
                    await evaluate("window.scrollTo({top:0,behavior:'instant'})");await asyncio.sleep(.1)
                    options={'format':'png','captureBeyondViewport':full}
                    if full:
                        dimensions=(await command('Page.getLayoutMetrics'))['cssContentSize']
                        options['clip']={'x':0,'y':0,'width':dimensions['width'],'height':dimensions['height'],'scale':1}
                    result=await command('Page.captureScreenshot',options)
                    (OUT/f'{name}.png').write_bytes(base64.b64decode(result['data']))
                async def layout(name):
                    result=await evaluate("""(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,main:document.querySelectorAll('main').length,h1:document.querySelectorAll('main h1').length,unlabeled:[...document.querySelectorAll('input,select')].filter(e=>!e.closest('label')&&!e.getAttribute('aria-label')&&!e.labels?.length).length,buttons:[...document.querySelectorAll('button')].filter(e=>!e.textContent.trim()&&!e.getAttribute('aria-label')).length}))()""")
                    assert result=={'overflow':False,'main':1,'h1':1,'unlabeled':0,'buttons':0},(name,result)
                    fit=await evaluate("[...document.querySelectorAll('main, [class*=overview], [class*=latestMarket], [class*=mapMain], details[class*=evidence]')].every(e=>{const r=e.getBoundingClientRect();return r.left>=-1&&r.right<=document.documentElement.clientWidth+1})")
                    assert fit,(name,'main panels exceed the available viewport')
                    checks.append(name)
                async def load_home(fresh=False):
                    await command('Page.navigate',{'url':URL+'/'})
                    await wait("document.readyState==='complete'&&!!document.querySelector('[data-market=us]')")
                    if fresh:
                        await evaluate("sessionStorage.removeItem('mpri-atlas-lens');sessionStorage.setItem('mpri-language','ko')")
                        await command('Page.reload')
                    await wait("document.documentElement?.lang==='ko'&&!!document.querySelector('[data-series]')")
                    await asyncio.sleep(.3);await evaluate('document.fonts.ready')
                async def limits():
                    return await evaluate("[...document.querySelectorAll('input[aria-label=\"조회 시작일 조절\"],input[aria-label=\"조회 종료일 조절\"]')].slice(0,2).map(el=>Number(el.value))")
                await command('Page.enable');await command('Runtime.enable')
                for width,height in [(1440,1000),(390,844)]:
                    await command('Emulation.setDeviceMetricsOverride',{'width':width,'height':height,'deviceScaleFactor':1,'mobile':False})
                    await load_home(True)
                    await layout(f'{width}px initial layout and accessible names')
                    assert await evaluate("!document.querySelector('.sidebar')&&!document.querySelector('.overview-intro')&&!document.querySelector('.observation-rail')")
                    assert await evaluate("document.querySelector('[data-market=us] [data-value=risk]').textContent==='N/A'")
                    assert await evaluate("document.querySelector('[data-market=us] [data-value=msi]').textContent==='N/A'")
                    assert await evaluate("document.querySelector('[data-market=korea] [data-value=risk]').textContent==='40.2%'")
                    assert await evaluate("document.querySelector('[data-market=korea] [data-value=msi]').textContent==='0.753'")
                    assert await evaluate("document.querySelector('[data-market=korea]').textContent.includes('2026-11-02')")
                    assert await evaluate("document.querySelector('[data-market=us]').textContent.includes('검증 보류')")
                    assert await evaluate("document.querySelector('[aria-label=\"최신 시장 위험 현황\"]').getBoundingClientRect().bottom<innerHeight")
                    assert await evaluate("document.querySelectorAll('[data-series]').length===4")
                    assert await evaluate("document.querySelectorAll('button[aria-pressed][class*=signalLabel]').length===6")
                    checks.append(f'{width}px latest scores/dates/status exact; no sidebar/hero/rail; four series and six signals')
                    await screenshot(f'{width}-main');await screenshot(f'{width}-full',True)
                    await click('3개월')
                    await wait("sessionStorage.getItem('mpri-atlas-lens')?.includes('3M')")
                    await set_input('input[aria-label="관측일 직접 선택"]','2026-09-16')
                    await wait("document.querySelector('input[type=date]').value==='2026-09-16'")
                    expected=next(p for p in data['korea'] if p['date']=='2026-09-16')['risk']
                    actual=await evaluate("document.querySelector('[data-series=\"korea-risk\"]').lastElementChild.textContent")
                    assert actual==f'{expected*100:.1f}%',(actual,expected)
                    signal_expected=next(r for r in monitor['history'] if r['Date']=='2026-09-16')['decline_1d_breadth_pct']
                    assert await evaluate("document.querySelector('[aria-label=\"한국 확산도 지표 6개의 관측일별 백분위\"]').firstElementChild.lastElementChild.textContent")==f'{signal_expected*100:.1f}%'
                    assert await evaluate("document.querySelector('[class*=sidebarMarkets] > div:first-child dd').textContent")==f'{expected*100:.1f}%'
                    assert await evaluate("document.querySelector('[class*=sidebarBreadth] > div b').textContent")==f'{signal_expected*100:.1f}%'
                    assert await evaluate("[...document.querySelectorAll('[data-series=\"korea-risk\"] rect title')].some(t=>t.textContent==='2026-09-16: "+f'{expected*100:.1f}%'+"')")
                    checks.append(f'{width}px exact-date heatmap, visible detail values and original breadth percentile')
                    await set_input('input[aria-label="관측일 직접 선택"]','2026-09-19')
                    await wait("document.querySelector('[data-series=\"korea-risk\"]').lastElementChild.textContent==='N/A'")
                    assert await evaluate("document.querySelector('[data-series=\"us-risk\"]').lastElementChild.textContent==='N/A'")
                    assert await evaluate("[...document.querySelectorAll('[data-series=\"korea-risk\"] rect title')].some(t=>t.textContent==='2026-09-19: N/A')")
                    checks.append(f'{width}px absent date stays N/A without carry-forward; missing cells identified')
                    await evaluate("(()=>{const s=document.querySelector('select[aria-label=\"표시 지표\"]');s.value='both';s.dispatchEvent(new Event('change',{bubbles:true}));})()")
                    await wait("document.querySelectorAll('[data-series]').length===4")
                    assert await evaluate("document.querySelector('section[aria-label=\"시장 위험 지도와 기간별 분석\"]').textContent.includes('시장별 개별 축')")
                    await click('3개월')
                    before=await limits()
                    await evaluate("document.querySelector('button[aria-label=\"선택일 중심으로 구간 확대\"]').click()")
                    await asyncio.sleep(.15)
                    after=await limits();assert after[1]-after[0]<before[1]-before[0],(before,after)
                    await evaluate("document.querySelector('button[aria-label=\"조회 구간 축소\"]').click()")
                    await asyncio.sleep(.15)
                    checks.append(f'{width}px four-series mode and centered zoom')
                    # Real pointer brush on the full-history navigator.
                    await evaluate("document.querySelector('details[class*=timelineOptions]').open=true")
                    bounds=await evaluate("(()=>{const r=document.querySelector('svg[aria-label^=\"전체 기간의\"]').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};})()")
                    await evaluate("document.querySelector('svg[aria-label^=\"전체 기간의\"]').scrollIntoView({block:'center'})")
                    bounds=await evaluate("(()=>{const r=document.querySelector('svg[aria-label^=\"전체 기간의\"]').getBoundingClientRect();return {x:r.x,y:r.y,w:r.width,h:r.height};})()")
                    start_x=bounds['x']+bounds['w']*.95;end_x=bounds['x']+bounds['w']*.995;y=bounds['y']+bounds['h']/2
                    await command('Input.dispatchMouseEvent',{'type':'mousePressed','x':start_x,'y':y,'button':'left','clickCount':1})
                    for step in range(1,5):
                        await command('Input.dispatchMouseEvent',{'type':'mouseMoved','x':start_x+(end_x-start_x)*step/4,'y':y,'button':'left','buttons':1})
                    await command('Input.dispatchMouseEvent',{'type':'mouseReleased','x':end_x,'y':y,'button':'left','clickCount':1})
                    await asyncio.sleep(.2)
                    brushed=await limits();assert brushed[0]<brushed[1]
                    assert not await evaluate("[...document.querySelectorAll('path')].some(el=>(el.getAttribute('d')||'').includes('NaN'))")
                    checks.append(f'{width}px real pointer interval selection and finite paths')
                    # Persisted time window and keyboard date step.
                    saved=await evaluate("JSON.parse(sessionStorage.getItem('mpri-atlas-lens'))")
                    await command('Page.reload');await wait("!!document.querySelector('[data-series]')")
                    await asyncio.sleep(.3)
                    restored=await evaluate("JSON.parse(sessionStorage.getItem('mpri-atlas-lens'))")
                    assert saved==restored,(saved,restored)
                    slider='input[aria-label="조회 관측일 이동"]'
                    await set_input(slider,0)
                    initial=await evaluate("document.querySelector('input[type=date]').value")
                    await command('Input.dispatchKeyEvent',{'type':'keyDown','key':'ArrowRight','code':'ArrowRight','windowsVirtualKeyCode':39})
                    await command('Input.dispatchKeyEvent',{'type':'keyUp','key':'ArrowRight','code':'ArrowRight','windowsVirtualKeyCode':39})
                    assert initial!=await evaluate("document.querySelector('input[type=date]').value")
                    await evaluate("document.querySelector('button[aria-pressed][class*=signalLabel]').click()")
                    await click('관측 근거 확인↘')
                    await wait("document.querySelector('details[class*=evidence]').open")
                    checks.append(f'{width}px saved lens state, keyboard date navigation and evidence')
                    await layout(f'{width}px layout after interactions')
                    await screenshot(f'{width}-selected',True)
                    await click('EN');await wait("document.documentElement?.lang==='en'")
                    await layout(f'{width}px English layout')
                    await screenshot(f'{width}-en')
                    await click('한국어');await wait("document.documentElement?.lang==='ko'")
                    await evaluate("document.querySelector('header details').open=true;document.querySelector('header details summary').focus()")
                    assert await evaluate("new Set([...document.querySelectorAll('header nav a')].map(a=>a.getAttribute('href'))).size===9")
                    await command('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
                    assert await evaluate("!document.querySelector('header details').open")
                    checks.append(f'{width}px all nine page links, language switch and Escape menu')
                # Non-home content retains its previous shell.
                await command('Page.navigate',{'url':URL+'/methodology'})
                await wait("location.pathname==='/methodology'&&!!document.querySelector('.sidebar')")
                checks.append('other-page shell remains unchanged')
                (OUT/'runtime-diagnostics.json').write_text(json.dumps({'exceptions':exceptions,'console_errors':console_errors},ensure_ascii=False,indent=2))
                assert not exceptions,exceptions
                assert not console_errors,console_errors
                report={'checks':checks,'count':len(checks),'javascript_exceptions':exceptions,'screenshots':str(OUT),
                        'browser':'Chromium via CDP','viewports':['1440x1000','390x844'],
                        'limitations':['not a full screen-reader or WCAG certification']}
                (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
        finally:
            process.terminate();process.wait(timeout=10)


if __name__=='__main__':asyncio.run(main())
