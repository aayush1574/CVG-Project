import { chromium } from '@playwright/test';
import { mkdir } from 'node:fs/promises';
await mkdir('qa/screenshots',{recursive:true});
const browser=await chromium.launch({headless:true});
const page=await browser.newPage({viewport:{width:1440,height:1000},deviceScaleFactor:1});
const errors=[];page.on('pageerror',e=>errors.push(e.message));
await page.goto('http://127.0.0.1:5174');
await page.getByRole('button',{name:'Start assessment',exact:true}).waitFor();
for(const section of await page.locator('.wm-reveal').all()){await section.scrollIntoViewIfNeeded();await page.waitForTimeout(100);}
await page.evaluate(()=>scrollTo(0,0));
await page.screenshot({path:'qa/screenshots/welcome-desktop.png',fullPage:true,animations:'disabled'});
await page.setViewportSize({width:390,height:844});
await page.screenshot({path:'qa/screenshots/welcome-mobile.png',fullPage:true,animations:'disabled'});
console.log(JSON.stringify({horizontalOverflow:await page.evaluate(()=>document.documentElement.scrollWidth>innerWidth),errors}));
await browser.close();
