"""Local Chromium CDP regression checks; no Playwright install or external pages.

MPRI_CHROMIUM=<existing chrome> [MPRI_BROWSER_LIBS=<temporary libraries>] \
MPRI_WEB_URL=http://127.0.0.1:3107 .venv/bin/python scripts/check_fintech_ui_browser.py
Screenshots and the report go to /tmp/mpri-ui-check by default, never source data.
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

WEB_URL = os.environ.get('MPRI_WEB_URL', 'http://127.0.0.1:3107')
OUT = Path(os.environ.get('MPRI_UI_OUTPUT', '/tmp/mpri-ui-check'))


async def run():
    if urllib.parse.urlsplit(WEB_URL).hostname not in {'127.0.0.1', 'localhost'}:
        raise ValueError('Local UI checks only')
    chrome = os.environ['MPRI_CHROMIUM']
    OUT.mkdir(parents=True, exist_ok=True)
    environment = dict(os.environ)
    if os.environ.get('MPRI_BROWSER_LIBS'):
        environment['LD_LIBRARY_PATH'] = os.environ['MPRI_BROWSER_LIBS']
    checks, errors = [], []
    with tempfile.TemporaryDirectory(prefix='mpri-ui-profile-') as profile, (OUT/'chromium.log').open('w') as log:
        process = subprocess.Popen([chrome, '--headless', '--no-sandbox', '--disable-dev-shm-usage',
            '--disable-background-networking', '--no-first-run', '--disable-sync',
            '--remote-debugging-port=0', f'--user-data-dir={profile}', 'about:blank'],
            env=environment, stdout=log, stderr=log)
        try:
            active = Path(profile)/'DevToolsActivePort'
            for _ in range(200):
                if active.exists(): break
                await asyncio.sleep(.1)
            port = active.read_text().splitlines()[0]
            targets = json.load(urllib.request.urlopen(f'http://127.0.0.1:{port}/json/list', timeout=10))
            url = next(t['webSocketDebuggerUrl'] for t in targets if t['type']=='page')
            async with websockets.connect(url, max_size=30_000_000) as ws:
                serial = 0
                async def command(method, params=None):
                    nonlocal serial
                    serial += 1
                    ident = serial
                    await ws.send(json.dumps({'id':ident, 'method':method, 'params':params or {}}))
                    while True:
                        response = json.loads(await asyncio.wait_for(ws.recv(), 30))
                        if response.get('method') == 'Runtime.exceptionThrown':
                            errors.append(response['params']['exceptionDetails'].get('text','exception'))
                        if response.get('id') == ident:
                            if 'error' in response: raise AssertionError(response)
                            return response.get('result',{})
                async def evaluate(js):
                    result = await command('Runtime.evaluate',{'expression':js,'returnByValue':True,'awaitPromise':True})
                    if 'exceptionDetails' in result: raise AssertionError(result['exceptionDetails'])
                    return result['result'].get('value')
                async def wait(js):
                    for _ in range(150):
                        if await evaluate(js): return
                        await asyncio.sleep(.1)
                    raise AssertionError('Timed out: '+js)
                async def navigate(path):
                    await command('Page.navigate',{'url':WEB_URL+path})
                    await wait(f"location.pathname==={json.dumps(path)} && document.readyState==='complete' && !!document.querySelector('main h1')")
                    await asyncio.sleep(.2)
                    await evaluate('document.fonts.ready')
                async def click(text, selector='button'):
                    await evaluate(f"""(()=>{{const el=[...document.querySelectorAll({json.dumps(selector)})].find(el=>el.textContent.trim()==={json.dumps(text)});if(!el || el.disabled)throw Error('Missing/enabled button: '+{json.dumps(text)});el.click();}})()""")
                async def set_input(selector, value):
                    await evaluate(f"""(()=>{{const el=document.querySelector({json.dumps(selector)});if(!el)throw Error('Input absent');el.focus();Object.getOwnPropertyDescriptor(HTMLInputElement.prototype,'value').set.call(el,{json.dumps(str(value))});el.dispatchEvent(new Event('input',{{bubbles:true}}));el.dispatchEvent(new Event('change',{{bubbles:true}}));}})()""")
                async def screenshot(name):
                    await evaluate('window.scrollTo(0,0)')
                    image = await command('Page.captureScreenshot',{'format':'png','captureBeyondViewport':False})
                    (OUT/f'{name}.png').write_bytes(base64.b64decode(image['data']))
                async def check_layout(name):
                    result=await evaluate("""(()=>({overflow:document.documentElement.scrollWidth>innerWidth+1,main:document.querySelectorAll('main').length,h1:document.querySelectorAll('main h1').length,unlabeled:[...document.querySelectorAll('input,select')].filter(e=>!e.closest('label')&&!e.getAttribute('aria-label')&&!e.labels?.length).map(e=>e.outerHTML.slice(0,120)),buttons:[...document.querySelectorAll('button')].filter(e=>!e.textContent.trim()&&!e.getAttribute('aria-label')).length}))()""")
                    assert not result['overflow'], (name,result)
                    assert result['main']==1 and result['h1']==1, (name,result)
                    assert not result['unlabeled'] and result['buttons']==0, (name,result)
                    checks.append(name)
                await command('Page.enable'); await command('Runtime.enable'); await command('Network.enable')
                for width in [1440,768,390]:
                    await command('Emulation.setDeviceMetricsOverride',{'width':width,'height':1000,'deviceScaleFactor':1,'mobile':False})
                    for path in ['/','/us','/korea','/breadth','/validation','/cases','/sources','/methodology','/portfolio']:
                        await navigate(path)
                        if path=='/portfolio': await wait("document.querySelector('main').textContent.includes('23.4%')")
                        await check_layout(f'{width}px {path}')
                        if path in ['/','/portfolio']: await screenshot(f'{width}-'+('home' if path=='/' else 'portfolio'))
                # Main explorer: input fidelity, keyboard inspection and session preferences.
                await command('Emulation.setDeviceMetricsOverride',{'width':1440,'height':1000,'deviceScaleFactor':1,'mobile':False})
                await navigate('/')
                assert await evaluate("[...document.querySelectorAll('.observation-row')][0].querySelector('strong').textContent==='N/A'")
                assert await evaluate("document.querySelector('.verified .observation-score strong').textContent==='40.2%'")
                await click('MSI'); await click('3M')
                await wait("sessionStorage.getItem('mpri-explorer')?.includes('3M')")
                await navigate('/')
                await wait("document.querySelector('[aria-label=\"탐색 지표\"] button[aria-pressed=true]').textContent==='MSI'")
                slider='input[aria-label="양시장 관측일 탐색"]'
                await set_input(slider,0)
                first=await evaluate("document.querySelector('.explorer-readout time').textContent")
                await command('Input.dispatchKeyEvent',{'type':'keyDown','key':'ArrowRight','code':'ArrowRight','windowsVirtualKeyCode':39})
                await command('Input.dispatchKeyEvent',{'type':'keyUp','key':'ArrowRight','code':'ArrowRight','windowsVirtualKeyCode':39})
                assert first != await evaluate("document.querySelector('.explorer-readout time').textContent")
                checks.append('explorer exact current N/A, saved metric/range and keyboard observation')
                # English remains persisted on all pages.
                await click('EN')
                await wait("document.documentElement.lang==='en'")
                await navigate('/methodology')
                await wait("document.documentElement.lang==='en'")
                assert await evaluate("document.querySelector('h1').textContent==='Methodology'")
                await click('KR')
                # Portfolio real API analysis, blocked Korean discovery and stale-result invalidation.
                await navigate('/portfolio')
                await wait("document.querySelector('main').textContent.includes('23.4%')")
                search='input[role="combobox"]'
                await set_input(search,'삼성')
                await wait("[...document.querySelectorAll('[role=option]')].some(el=>el.textContent.includes('005930'))")
                assert await evaluate("[...document.querySelectorAll('[role=option]')].find(el=>el.textContent.includes('005930')).getAttribute('aria-disabled')==='true'")
                await command('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
                assert await evaluate("[...document.querySelectorAll('button')].find(el=>el.textContent.trim()==='분석 ↗').disabled")
                assert not await evaluate("document.querySelector('main').textContent.includes('23.4%')")
                await set_input(search,'ａａｐｌ')
                await command('Input.dispatchKeyEvent',{'type':'keyDown','key':'Enter','code':'Enter','windowsVirtualKeyCode':13})
                await wait("document.querySelector('input[role=combobox]').value.includes('AAPL')")
                await click('분석 ↗')
                await wait("document.querySelector('main').textContent.includes('23.4%')")
                await click('스트레스 시나리오')
                assert await evaluate("document.querySelector('[role=tabpanel]:not([hidden])').textContent.includes('주식시장 급락')")
                await click('What-if 비교')
                await click('예시: 30%를 장기국채(TLT)로')
                await click('비교 ↗')
                await wait("!!document.querySelector('[role=tabpanel]:not([hidden]) table')")
                assert await evaluate("document.querySelector('[role=tabpanel]:not([hidden])').textContent.includes('23.4%')")
                await screenshot('desktop-whatif')
                checks.append('portfolio search/NFKC, blocked KR, stale result invalidation, real analysis/scenarios/what-if')
                # Keyboard tab navigation and loading/error states.
                await evaluate("document.getElementById('tab-whatif').focus()")
                await command('Input.dispatchKeyEvent',{'type':'keyDown','key':'Home','code':'Home','windowsVirtualKeyCode':36})
                await wait("document.getElementById('tab-diagnosis').getAttribute('aria-selected')==='true'")
                await command('Network.emulateNetworkConditions',{'offline':False,'latency':1500,'downloadThroughput':-1,'uploadThroughput':-1})
                await click('분석 ↗')
                await wait("!!document.querySelector('[aria-label=\"위험 분석 결과를 불러오는 중\"]')")
                await wait("document.querySelector('main').textContent.includes('23.4%')")
                await command('Network.emulateNetworkConditions',{'offline':False,'latency':0,'downloadThroughput':-1,'uploadThroughput':-1})
                await command('Network.setBlockedURLs',{'urls':['*api/portfolio/analyze*']})
                await click('분석 ↗')
                await wait("!!document.querySelector('[role=alert]')")
                assert not await evaluate("document.querySelector('main').textContent.includes('23.4%')")
                await screenshot('portfolio-error')
                await command('Network.setBlockedURLs',{'urls':[]})
                await click('분석 ↗');await wait("document.querySelector('main').textContent.includes('23.4%')")
                checks.append('keyboard workspace tabs, loading skeleton, error/empty state, retry')
                # Mobile navigation trap/Escape, both languages and reduced motion.
                await command('Emulation.setDeviceMetricsOverride',{'width':390,'height':844,'deviceScaleFactor':1,'mobile':False})
                await navigate('/')
                await evaluate("document.querySelector('.mobile-topbar button').click()")
                await wait("document.querySelector('.sidebar').classList.contains('is-open')")
                await click('EN')
                await command('Input.dispatchKeyEvent',{'type':'keyDown','key':'Escape','code':'Escape','windowsVirtualKeyCode':27})
                await wait("!document.querySelector('.sidebar').classList.contains('is-open')")
                assert await evaluate("document.activeElement===document.querySelector('.mobile-topbar button')")
                await check_layout('390px English home')
                await screenshot('390-en-home')
                await command('Emulation.setEmulatedMedia',{'features':[{'name':'prefers-reduced-motion','value':'reduce'}]})
                assert await evaluate("getComputedStyle(document.querySelector('.sidebar')).transitionDuration==='0s'")
                checks.append('mobile navigation/Escape focus return, English and reduced motion')
                assert not errors, errors
                report={'checks':checks,'count':len(checks),'javascript_exceptions':errors,'browser':'installed Chromium via CDP','url':WEB_URL,'screenshots':str(OUT),'limits':['manual contrast/keyboard checks are not a full WCAG certification']}
                (OUT/'results.json').write_text(json.dumps(report,ensure_ascii=False,indent=2)+'\n')
                print(json.dumps(report,ensure_ascii=False,indent=2),flush=True)
        finally:
            process.terminate()
            process.wait(timeout=10)


if __name__=='__main__':
    asyncio.run(run())
