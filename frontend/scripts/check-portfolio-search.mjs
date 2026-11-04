// Local production E2E. Supply Playwright via MPRI_PLAYWRIGHT_MODULE if installed externally.
import { createRequire } from 'node:module';
import assert from 'node:assert/strict';
const { chromium } = createRequire(import.meta.url)(process.env.MPRI_PLAYWRIGHT_MODULE || 'playwright');
(async () => {
 const browser = await chromium.launch({headless:true,executablePath:process.env.MPRI_CHROMIUM_PATH});
 try {
  for (const width of [390,1280]) {
   const page = await browser.newPage({viewport:{width,height:900}});
   await page.route('**/api/portfolio/v2/catalog',async route => {
    const response = await route.fetch(); const catalog = await response.json();
    catalog.assets.push({asset_id:'TEST:000001',ticker:'000001',name:'Synthetic blocked',name_ko:'가상 차단 종목',type:'stock',market:'KR',currency:'KRW',support_status:'unsupported',selectable:false,reason_codes:['RIGHTS_UNCONFIRMED']});
    await route.fulfill({json:catalog});
   });
   await page.goto('http://127.0.0.1:3000/portfolio');
   const box = page.getByRole('combobox',{name:'자산 1',exact:true}).first();
   await box.waitFor();
   await page.getByText('23.4%',{exact:true}).first().waitFor();
   await box.click(); await box.fill('엔비디아');
   await page.getByRole('option').filter({hasText:'NVDA'}).waitFor();
   await box.press('Enter'); assert.match(await box.inputValue(),/NVDA/);
   assert.equal(await page.getByText('23.4%',{exact:true}).count(),0);
   await box.click(); await box.fill('000001');
   const blocked = page.getByRole('option').filter({hasText:'000001'});
   await blocked.waitFor(); assert.equal(await blocked.getAttribute('aria-disabled'),'true');
   assert.match(await blocked.innerText(),/공개 데이터 사용 권리/);
   await box.press('Enter'); assert.equal(await box.inputValue(),'000001');
   assert.equal(await page.getByRole('button',{name:'분석',exact:true}).isEnabled(),false);
   await box.fill('ａａｐｌ'); await box.press('Enter');
   assert.match(await box.inputValue(),/AAPL/); await box.press('Escape');
   await page.evaluate(() => sessionStorage.setItem('mpri-language','en')); await page.reload();
   const english = page.getByRole('combobox',{name:'Asset 1',exact:true}).first();
   await english.waitFor(); await english.click(); await english.fill('Microsoft');
   await page.getByRole('option').filter({hasText:'MSFT'}).waitFor();
   await english.press('ArrowDown'); await english.press('Enter'); assert.match(await english.inputValue(),/MSFT/);
   assert.ok(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth),'page must fit viewport');
   await page.close();
  }
  console.log('PASS: 390/1280px, KR/EN names, NFKC ticker, keyboard, unsupported reason/blocking, invalidation');
 } finally { await browser.close(); }
})().catch(error => { console.error(error);process.exitCode=1; });
