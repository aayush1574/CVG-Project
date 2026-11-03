import {chromium,expect} from '@playwright/test';
const browser=await chromium.launch();const context=await browser.newContext();const page=await context.newPage();
const base=process.env.CVG_UI_URL||'http://127.0.0.1:5175';
try{
 await page.goto(base);
 // Structured imports must retain categorical values and never fill blanks.
 await page.getByRole('button',{name:'Assessment',exact:true}).click();
 await page.getByLabel('Select laboratory report').setInputFiles({name:'inputs.json',mimeType:'application/json',buffer:Buffer.from(JSON.stringify({age:55,sex:'male',creatinine:1,glucose:100}))});
 await expect(page.getByText(/4 values extracted/)).toBeVisible();
 await page.getByRole('button',{name:'Review inputs',exact:true}).click();
 await expect(page.locator('#review-sex')).toHaveValue('male');
 let calls=0;
 await page.route('**/api/predict',async route=>{calls++;await route.fulfill({status:422,contentType:'application/json',body:JSON.stringify({detail:'Test invalid recording'})});});
 await page.getByRole('button',{name:'Generate research report'}).click();
 await expect(page.getByText('Test invalid recording',{exact:true})).toBeVisible();expect(calls).toBe(1);
 await page.unroute('**/api/predict');
 let release;const gate=new Promise(resolve=>release=resolve);let started;
 const pending=new Promise(resolve=>started=resolve);
 await page.route('**/api/predict',async route=>{started();await gate;await route.abort().catch(()=>{});});
 await page.getByRole('button',{name:'Generate research report'}).click();await pending;
 await page.locator('#review-age').fill('60');release();
 await expect(page.getByRole('button',{name:'Generate research report'})).toBeEnabled();
 await expect(page.getByRole('heading',{name:'Your research report.'})).toHaveCount(0);
 await page.unroute('**/api/predict');
 let retries=0;await page.route('**/api/predict',async route=>{retries++;if(retries===1)await route.fulfill({status:503,body:'warming'});else await route.continue();});
 await page.getByRole('button',{name:'Generate research report'}).click();
 await expect(page.getByRole('heading',{name:'Your research report.'})).toBeVisible({timeout:120000});expect(retries).toBe(2);
 await expect(page.getByText('Atrial fibrillation rhythm model',{exact:true})).toHaveCount(0);
 console.log('PASS: structured roundtrip, 422 without retry, cancellation after edit, transient retry, clinical-only report');
}finally{await browser.close();}
