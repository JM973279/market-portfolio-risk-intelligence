// Local-only version matrix. Run against real production builds and API proxies.
const assert = require('node:assert/strict');
const fs = require('node:fs');
const { chromium } = require(process.env.PLAYWRIGHT_MODULE || 'playwright');
const base = process.env.MPRI_WEB_URL;
assert.ok(base && ['127.0.0.1', 'localhost'].includes(new URL(base).hostname), 'Loopback web required');
const blocked = process.env.MPRI_EXPECT_CATALOG_404 === '1';
const reference = JSON.parse(fs.readFileSync(process.env.MPRI_BASELINE_PATH, 'utf8'));
const output = process.env.MPRI_RESULT_PATH;
assert.ok(output, 'Result path required');
const before = JSON.parse(fs.readFileSync('examples/portfolio/before.json'));
const after = JSON.parse(fs.readFileSync('examples/portfolio/after.json'));
const result = { web: process.env.MPRI_WEB_VERSION, api: process.env.MPRI_API_VERSION,
  scope: 'loopback_production_builds', expected_incompatible: blocked, contracts: [], viewports: [] };
const pct = (v, d=1) => `${v < 0 ? '−' : ''}${Math.abs(v).toLocaleString('en-US', {minimumFractionDigits:d, maximumFractionDigits:d})}%`;
async function request(path, body) {
 const r = await fetch(base + '/api/portfolio/' + path, body ? {method:'POST', headers:{'Content-Type':'application/json'}, body:JSON.stringify(body)} : {});
 return {status:r.status, body:await r.json()};
}
(async () => {
 for (const [path, body, key] of [['universe',null,'/api/portfolio/universe'], ['scenarios',null,'/api/portfolio/scenarios'],
  ['analyze',before,'before'], ['analyze',after,'after'], ['compare',{current:before,proposed:after},'compare']]) {
  assert.deepEqual(await request(path,body), reference[key]); result.contracts.push(key);
 }
 assert.equal((await request('analyze',{})).status,422);
 assert.equal((await request('v2/catalog')).status, process.env.MPRI_API_VERSION === 'old' ? 404 : 200);
 const browser = await chromium.launch({executablePath:process.env.CHROMIUM_EXECUTABLE, headless:true});
 try {
  for (const width of [390,1280]) {
   const ctx = await browser.newContext({viewport:{width,height:1000}});
   await ctx.addInitScript(() => sessionStorage.setItem('mpri-language','en'));
   const page = await ctx.newPage(); page.setDefaultTimeout(15000);
   const errors=[]; page.on('pageerror',e => errors.push(e.message));
   // Market exports are independent of the Portfolio API version.
   for (const route of ['/korea','/us']) {
    assert.equal((await page.goto(base+route)).status(),200);
    const op=page.locator('.operational-market'); await op.waitFor();
    const current=await op.locator('.selected-metrics').first().innerText();
    if (route==='/korea') for (const v of ['40.2%','0.753','1.115','2026-11-02']) assert.ok(current.includes(v),v);
    else {
     assert.equal(await op.locator('.selected-metrics').first().getByText('N/A',{exact:true}).count(),4);
     assert.ok((await op.innerText()).includes('2026-10-02'));
     assert.ok((await op.locator('.selected-metrics').last().innerText()).includes('10.0%'));
    }
    assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   }
   await page.goto(base+'/portfolio');
   const hidden=page.getByRole('heading',{name:'Hidden Risk Map',exact:true});
   const alert=page.locator('main').getByRole('alert');
   if (blocked) {
    await alert.waitFor(); assert.equal(await hidden.count(),0);
    assert.ok(await page.getByRole('button',{name:'Analyze',exact:true}).isDisabled());
    assert.ok(await page.getByRole('button',{name:'Compare',exact:true}).isDisabled());
   } else {
    await hidden.waitFor();
    const a=reference.before.body;
    const expected=[pct(a.volatility),pct(a.concentration.max_asset.weight),pct(a.concentration.max_sector.weight),a.factor_exposure.market.toFixed(2)];
    assert.deepEqual(await page.locator('main > .selected-metrics strong').allTextContents(),expected);
    const correlation=page.locator('section').filter({has:page.getByRole('heading',{name:'Correlation',exact:true})});
    assert.deepEqual(await correlation.locator('tbody td').allTextContents(),a.correlation.matrix.flat().map(x=>x.toFixed(2)));
    for (const s of a.stress) {
     const title={equity_selloff:'Equity sell-off',rate_shock:'Interest rate shock',volatility_shock:'Volatility shock'}[s.scenario];
     const section=page.locator('section').filter({has:page.getByRole('heading',{name:title,exact:true})});
     assert.equal(await section.locator('[class*="headline"] strong').innerText(),pct(Math.abs(s.loss_pct)));
    }
    const response=page.waitForResponse(r=>r.url().endsWith('/api/portfolio/compare')&&r.request().method()==='POST');
    await page.getByRole('button',{name:'Compare',exact:true}).click();
    const r=await response; assert.equal(r.status(),200); assert.deepEqual(await r.json(),reference.compare.body);
    await page.getByRole('cell',{name:'16.94%',exact:true}).waitFor();
    const table=page.locator('table').filter({has:page.getByRole('columnheader',{name:'Changed',exact:true})});
    assert.equal(await table.locator('tbody tr').count(),reference.compare.body.comparison.length);
    const weight=page.getByRole('spinbutton',{name:'Weight (%) 1',exact:true}).first();
    await weight.fill('31'); assert.ok(await page.getByRole('button',{name:'Analyze',exact:true}).isDisabled());
    assert.equal(await hidden.count(),0); assert.equal(await page.getByRole('cell',{name:'16.94%',exact:true}).count(),0);
   }
   // Error injection remains in the browser; no fault route is deployed.
   const pattern=blocked?'**/api/portfolio/v2/catalog':'**/api/portfolio/analyze';
   for (const status of [422,500,503,504]) {
    await page.route(pattern,route=>route.fulfill({status,json:{detail:status===422?[{msg:'QA invalid'}]:{code:'QA_resource_or_deadline'}}}));
    await page.goto(base+'/portfolio'); await alert.waitFor(); assert.equal(await hidden.count(),0);
    await page.unroute(pattern);
   }
   await page.route('**/api/portfolio/**',route=>route.abort());
   await page.goto(base+'/portfolio'); await alert.waitFor(); assert.equal(await hidden.count(),0);
   await page.unroute('**/api/portfolio/**');
   await page.goto(base+'/portfolio');
   if (blocked) await alert.waitFor(); else await hidden.waitFor();
   assert.ok(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth));
   assert.deepEqual(errors,[]);
   result.viewports.push({width,market:true,portfolio:blocked?'blocked_catalog_404':'passed',
     stress:blocked?'blocked_catalog_404':'passed',whatif:blocked?'blocked_catalog_404':'passed',
     error_statuses:[422,500,503,504],network_recovery:true,page_errors:errors});
   await ctx.close();
  }
 } finally { await browser.close(); }
 result.verdict=blocked?'INCOMPATIBLE_EXPECTED':'PASS';
 fs.writeFileSync(output,JSON.stringify(result,null,2)+'\n'); console.log(JSON.stringify(result));
})().catch(e=>{console.error(e);process.exitCode=1});
