import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 900 }, reducedMotion: 'no-preference' });
const page = await context.newPage();
const checks = [], failures = [], errors = [], unexpectedRequests = [];
const origin = 'http://127.0.0.1:5174';
function trackContext(ctx) {
  ctx.on('request', request => {
    const url = new URL(request.url());
    if (!['http:', 'https:'].includes(url.protocol)) return;
    if (url.origin !== origin || request.method() !== 'GET' || /\/(?:api|predict|analyze|analyse)(?:\/|$)/i.test(url.pathname)) {
      unexpectedRequests.push({ url: request.url(), method: request.method() });
    }
  });
  ctx.on('page', child => child.on('pageerror', error => errors.push(error.message)));
}
trackContext(context);
page.on('pageerror', error => errors.push(error.message));
await mkdir('qa/screenshots', { recursive: true });
async function check(name, run) {
  try { await run(); checks.push(name); console.log('PASS ' + name); }
  catch (error) { failures.push({ name, error: error.message }); console.log('FAIL ' + name + ': ' + error.message); }
}
const field = page.locator('.wm-contour-field');
const workflow = page.locator('.wm-workflow');
const tab = index => page.getByRole('tab', { name: ['01 Bring your details', '02 Make it yours', '03 Explore the picture'][index], exact: true });
const paths = target => target.locator('.wm-contour-lines path').evaluateAll(elements => elements.map(element => element.getAttribute('d')));
const leave = () => page.mouse.move(20, 20);
const settled = (target = field) => expect(target).toHaveAttribute('data-morph-state', 'settled', { timeout: 7000 });
async function observePaths() {
  await field.evaluate(svg => {
    window.__morphObserver?.disconnect();
    const first = svg.querySelector('path');
    window.__morphSamples = new Set([first.getAttribute('d')]);
    window.__morphObserver = new MutationObserver(() => window.__morphSamples.add(first.getAttribute('d')));
    window.__morphObserver.observe(first, { attributes: true, attributeFilter: ['d'] });
  });
}
async function sampledCount() {
  return page.evaluate(() => { window.__morphObserver.disconnect(); return window.__morphSamples.size; });
}

try {
  await page.goto(origin);
  await workflow.scrollIntoViewIfNeeded();
  await leave();
  await settled();

  await check('Chapter selection changes real SVG geometry through intermediate vector shapes', async () => {
    const before = await paths(field);
    await observePaths();
    await tab(1).click();
    await expect(tab(1)).toHaveAttribute('aria-selected', 'true');
    await expect(page.getByRole('heading', { name: 'Every detail deserves a second look.', exact: true })).toBeVisible();
    await expect(workflow).toHaveAttribute('data-interaction-state', 'morphing');
    await leave();
    await settled();
    expect(await sampledCount()).toBeGreaterThan(2);
    const after = await paths(field);
    expect(after).not.toEqual(before);
    expect(after.every(path => path && !/NaN|Infinity/.test(path))).toBe(true);
  });

  await check('Rapid interrupted selections finish at the latest chapter without stale completion', async () => {
    await tab(2).click(); await leave(); await settled();
    const reference = await paths(field);
    for (const index of [0, 1, 2, 0, 1, 2]) await tab(index).click({ force: true });
    await leave();
    await expect(tab(2)).toHaveAttribute('aria-selected', 'true');
    await expect(field).toHaveAttribute('data-morph-chapter', '2');
    await settled();
    expect(await paths(field)).toEqual(reference);
    await expect(workflow).not.toHaveAttribute('data-interaction-state', 'morphing');
  });

  await check('Settled geometry stops scheduling paint work', async () => {
    await leave(); await settled();
    const before = await field.getAttribute('data-morph-frame');
    const geometry = await paths(field);
    await page.waitForTimeout(250);
    expect(await field.getAttribute('data-morph-frame')).toBe(before);
    expect(await paths(field)).toEqual(geometry);
  });

  await check('Pointer movement deforms path data and press cancellation releases the state', async () => {
    await workflow.scrollIntoViewIfNeeded();
    const box = await workflow.boundingBox();
    await page.mouse.move(box.x + box.width * .65, box.y + 25);
    await settled();
    const before = await paths(field);
    await page.mouse.move(box.x + box.width * .9, box.y + box.height * .7);
    await expect.poll(() => paths(field)).not.toEqual(before);
    await page.mouse.down();
    await expect(workflow).toHaveAttribute('data-interaction-state', 'pressed');
    await workflow.dispatchEvent('pointercancel', { pointerId: 1, pointerType: 'mouse', bubbles: true });
    await expect(workflow).not.toHaveAttribute('data-interaction-state', 'pressed');
    await leave(); await page.mouse.up(); await settled();
  });

  await check('Keyboard selection drives the same morph while preserving focus and content', async () => {
    await tab(0).focus(); await page.keyboard.press('Home'); await settled();
    const before = await paths(field);
    await page.keyboard.press('ArrowRight');
    await expect(tab(1)).toBeFocused();
    await expect(tab(1)).toHaveAttribute('aria-selected', 'true');
    await expect(field).toHaveAttribute('data-morph-chapter', '1');
    await settled();
    expect(await paths(field)).not.toEqual(before);
  });

  await check('Manual pause keeps selected content live while all vector motion stays static', async () => {
    await page.getByRole('button', { name: 'Pause animations', exact: true }).click();
    await workflow.scrollIntoViewIfNeeded();
    await expect(workflow).toHaveAttribute('data-interaction-state', 'suspended');
    await expect(field).toHaveAttribute('data-morph-state', 'paused');
    await tab(2).click();
    await expect(tab(2)).toHaveAttribute('aria-selected', 'true');
    await expect(field).toHaveAttribute('data-morph-chapter', '2');
    const before = await paths(field);
    const frame = await field.getAttribute('data-morph-frame');
    const box = await workflow.boundingBox();
    await page.mouse.move(box.x + box.width * .8, box.y + 25);
    await page.waitForTimeout(250);
    expect(await paths(field)).toEqual(before);
    expect(await field.getAttribute('data-morph-frame')).toBe(frame);
    await page.getByRole('button', { name: 'Enable animations', exact: true }).click();
    await workflow.scrollIntoViewIfNeeded(); await leave(); await settled();
  });

  await check('Reduced motion cancels an in-flight morph and shows the selected vector immediately', async () => {
    await tab(0).click();
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(field).toHaveAttribute('data-morph-state', 'paused');
    await expect(workflow).toHaveAttribute('data-interaction-state', 'suspended');
    await tab(1).click();
    await expect(field).toHaveAttribute('data-morph-chapter', '1');
    const before = await paths(field);
    const frame = await field.getAttribute('data-morph-frame');
    await page.waitForTimeout(250);
    expect(await paths(field)).toEqual(before);
    expect(await field.getAttribute('data-morph-frame')).toBe(frame);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await leave(); await settled();
  });

  await check('Offscreen vectors suspend and resume cleanly without background paint work', async () => {
    await page.setViewportSize({ width: 1440, height: 700 });
    await workflow.scrollIntoViewIfNeeded();
    await tab(2).click();
    await page.evaluate(() => window.scrollTo({ top: document.documentElement.scrollHeight, behavior: 'instant' }));
    await expect(field).toHaveAttribute('data-morph-state', 'suspended');
    const frame = await field.getAttribute('data-morph-frame');
    await page.waitForTimeout(250);
    expect(await field.getAttribute('data-morph-frame')).toBe(frame);
    await workflow.scrollIntoViewIfNeeded(); await leave(); await settled();
    await expect(tab(2)).toHaveAttribute('aria-selected', 'true');
    await page.evaluate(() => window.getSelection()?.removeAllRanges());
    await page.screenshot({ path: 'qa/screenshots/state-morph-workflow.png', fullPage: false, animations: 'disabled' });
  });

  await check('Navigation during a morph cleans up and remounts a working state machine', async () => {
    await tab(0).click();
    await page.getByRole('button', { name: 'Assessment', exact: true }).click();
    await expect(field).toHaveCount(0);
    await page.waitForTimeout(200);
    await page.getByRole('button', { name: 'Overview', exact: true }).click();
    await workflow.scrollIntoViewIfNeeded(); await leave(); await settled();
    await tab(1).click(); await leave(); await settled();
    await expect(field).toHaveAttribute('data-morph-chapter', '1');
  });

  const touchContext = await browser.newContext({ viewport: { width: 390, height: 844 }, hasTouch: true, isMobile: true, reducedMotion: 'no-preference' });
  trackContext(touchContext);
  const touch = await touchContext.newPage();
  await check('Touch selection morphs the same vectors without trapping the pressed state', async () => {
    await touch.goto(origin);
    const touchField = touch.locator('.wm-contour-field');
    const touchWorkflow = touch.locator('.wm-workflow');
    await touchWorkflow.scrollIntoViewIfNeeded(); await settled(touchField);
    const before = await paths(touchField);
    await touch.getByRole('tab', { name: '03 Explore the picture', exact: true }).tap();
    await expect(touch.getByRole('tab', { name: '03 Explore the picture', exact: true })).toHaveAttribute('aria-selected', 'true');
    await settled(touchField);
    await expect(touchWorkflow).not.toHaveAttribute('data-interaction-state', 'pressed');
    expect(await paths(touchField)).not.toEqual(before);
    expect(await touch.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  });
  await touchContext.close();

  await check('State and morph interactions have no runtime errors or external/backend requests', async () => {
    expect(errors).toEqual([]);
    expect(unexpectedRequests).toEqual([]);
  });
  await writeFile('qa/state-morph-results.json', JSON.stringify({ checks, failures, errors, unexpectedRequests }, null, 2));
  console.log(JSON.stringify({ passed: checks.length, failed: failures.length, errors }, null, 2));
} finally { await browser.close(); }
if (failures.length) process.exitCode = 1;
