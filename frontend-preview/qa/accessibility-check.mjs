import {chromium,expect} from '@playwright/test';
import AxeBuilder from '@axe-core/playwright';
import {writeFile} from 'node:fs/promises';
const browser=await chromium.launch({headless:true});
const context=await browser.newContext({viewport:{width:1440,height:1000},reducedMotion:'reduce'});
const page=await context.newPage();
const reports=[];
async function audit(name){const r=await new AxeBuilder({page}).withTags(['wcag2a','wcag2aa','wcag21aa']).analyze();reports.push({name,violations:r.violations.map(v=>({id:v.id,impact:v.impact,nodes:v.nodes.map(n=>({html:n.html,target:n.target,summary:n.failureSummary}))}))});}
try{
await page.goto('http://127.0.0.1:5174');await audit('welcome');
for(const width of [320,390,768,1024,1440]){await page.setViewportSize({width,height:900});expect(await page.evaluate(()=>document.documentElement.scrollWidth<=innerWidth)).toBe(true);if(width<=700){const box=await page.locator('.hero-photo').boundingBox();expect(box.width).toBe(width);}}
await page.setViewportSize({width:1440,height:1000});await page.getByRole('button',{name:'Start assessment',exact:true}).click();await audit('upload');
await page.getByRole('tab',{name:'Enter details',exact:true}).click();await audit('manual');
await page.getByRole('button',{name:'CardioScope home'}).click();await page.getByRole('button',{name:'Try a sample',exact:true}).click();await page.getByRole('button',{name:'Explore sample',exact:true}).click();await audit('review');
await page.getByRole('button',{name:'View sample report',exact:true}).click();await audit('report');
await writeFile('qa/accessibility-results.json',JSON.stringify(reports,null,2));
console.log(JSON.stringify(reports.map(r=>({screen:r.name,violations:r.violations.map(v=>({id:v.id,count:v.nodes.length,example:v.nodes[0]}))})),null,2));
expect(reports.flatMap(r=>r.violations)).toEqual([]);
}finally{await browser.close();}
