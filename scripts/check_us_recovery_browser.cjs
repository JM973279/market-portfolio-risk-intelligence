// Requires Playwright + Chromium; accepts the same environment overrides as release QA.
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const assert = require('node:assert/strict');
const fs = require('node:fs');
let browser;

(async () => {
 const base = process.env.MPRI_WEB_URL || 'http://127.0.0.1:3107';
 browser = await chromium.launch({headless:true, args:['--no-sandbox']});
 const page = await browser.newPage({viewport:{width:1440,height:1000}});
 const errors = [];
 page.on('pageerror', error => errors.push(error.message));
 const response = await page.request.get(base + '/data/operational-markets.json');
 assert.equal(response.status(), 200);
 const data = await response.json(), us = data.markets.us;
 const point = us.lastValid, price = us.priceHistory.at(-1);
 assert.ok(point.date < price.date, 'Fixture must exercise credit publication lag');
 assert.equal(us.current, null);

 assert.equal((await page.goto(base + '/us')).status(), 200);
 const panel = page.locator('.operational-market');
 const metrics = panel.locator('.selected-metrics').first();
 await metrics.getByText(point.date, {exact:true}).waitFor();
 const expected = [(point.risk*100).toFixed(1)+'%', point.msi.toFixed(3), point.threshold.toFixed(3), point.date];
 assert.deepEqual(await metrics.locator('strong').allTextContents(), expected);
 assert.ok((await panel.innerText()).includes(price.price.toFixed(2)+' USD'));
 assert.ok((await panel.getByRole('status').innerText()).includes('검증된 추론'));
 const chart = panel.locator('.market-chart');
 const index = chart.locator('svg path[stroke="#173f70"]');
 const initialPath = await index.getAttribute('d');
 assert.ok(initialPath.length > 100 && !initialPath.includes('NaN'));
 assert.ok((await chart.locator('svg path[stroke="#eb6874"]').getAttribute('d')).length > 20);
 await chart.getByRole('button', {name:'1M',exact:true}).click();
 assert.notEqual(await index.getAttribute('d'), initialPath);
 const slider = chart.locator('input[type=range]');
 await slider.focus();
 await slider.press('End');
 assert.equal(await chart.locator('.chart-readout time').innerText(),price.date);
 assert.equal(await chart.locator('.risk-readout b').innerText(),'N/A');
 await slider.press('ArrowLeft');
 assert.equal(await chart.locator('.chart-readout time').innerText(),point.date);
 assert.equal(await chart.locator('.risk-readout b').innerText(),expected[0]);
 await page.screenshot({path:'/tmp/mpri-us-recovery-desktop.png',fullPage:true});

 await page.getByRole('button',{name:'EN',exact:true}).click();
 await page.waitForFunction(()=>document.documentElement.lang==='en');
 assert.ok((await panel.getByRole('status').innerText()).includes('Verified inference'));
 assert.ok((await panel.innerText()).includes('Latest verified Risk Score'));
 assert.ok((await chart.getByRole('heading').innerText()).includes('US observed prices'));

 assert.equal((await page.goto(base + '/')).status(),200);
 await page.waitForFunction(()=>document.documentElement.lang==='en');
 const card=page.locator('.country-card').filter({has:page.locator('a[href="/us"]')});
 assert.equal(await card.locator('.country-metric strong').first().innerText(),expected[0]);
 assert.ok((await card.locator('.source-date').innerText()).includes(point.date));
 const homeChart=page.locator('.market-chart').first();
 assert.ok((await homeChart.getByRole('heading').innerText()).includes('US observed prices'));
 assert.ok((await homeChart.locator('svg path[stroke="#173f70"]').getAttribute('d')).length>100);

 await page.setViewportSize({width:360,height:844});
 await page.goto(base + '/us');
 assert.equal(await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),false);
 assert.deepEqual(await page.locator('.operational-market .selected-metrics').first().locator('strong').allTextContents(),expected);
 await page.screenshot({path:'/tmp/mpri-us-recovery-mobile.png',fullPage:true});
 assert.deepEqual(errors,[]);
 const result={status:'passed',priceDate:price.date,scoreDate:point.date,metrics:expected,
  checks:['real rendered paths','date range changes','keyboard observation selection','no score carried to price-only date','home metrics/chart','KR/EN','360px no overflow'],errors};
 fs.writeFileSync('/tmp/mpri-us-recovery-browser.json',JSON.stringify(result,null,2));
 console.log(JSON.stringify(result,null,2));
 await browser.close();
})().catch(async error=>{await browser?.close();console.error(error);process.exit(1)});
