import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';

const browser = await chromium.launch({ headless: true });
const context = await browser.newContext({ viewport: { width: 1440, height: 1000 }, reducedMotion: 'no-preference' });
const page = await context.newPage();
const errors = [], checks = [], failures = [], mediaRequests = [], unexpectedRequests = [];
function trackRequests(request) {
  const url = new URL(request.url());
  if (!['http:', 'https:'].includes(url.protocol)) return;
    if(url.origin==='http://127.0.0.1:5175' && url.pathname==='/api/health' && request.method()==='GET')return;
  if (url.origin !== 'http://127.0.0.1:5175' || /\/(?:api|predict|analyze|analyse)(?:\/|$)/i.test(url.pathname) || request.method() !== 'GET') {
    unexpectedRequests.push({ url: request.url(), method: request.method() });
  }
}
context.on('request', trackRequests);
page.on('pageerror', error => errors.push(error.message));
page.on('request', request => { if (request.url().includes('.mp4')) mediaRequests.push(request.url()); });
await mkdir('qa/screenshots', { recursive: true });
async function check(name, run) { try { await run(); checks.push(name); console.log('PASS ' + name); } catch (error) { failures.push({ name, error: error.message }); console.log('FAIL ' + name + ': ' + error.message); } }
const visualTransform = locator => locator.evaluate(element => {
  const style = getComputedStyle(element);
  return JSON.stringify({ transform: style.transform, translate: style.translate, scale: style.scale });
});
const scrollTo = y => page.evaluate(top => window.scrollTo({ top, behavior: 'instant' }), y);

try {
  await page.goto('http://127.0.0.1:5175/');
  await page.locator('.wm-welcome').waitFor();
  const heroVideo = page.locator('.wm-hero-media video');
  await check('Kinetic heading preserves a complete accessible name', async () => {
    await expect(page.getByRole('heading', { level: 1 })).toHaveAccessibleName(/CardioScope\.?\s*Your heart,\s*in focus\./);
    await expect(page.locator('#welcome-title')).toBeVisible();
  });
  await check('Visible background video autoplays muted', async () => {
    await expect.poll(() => heroVideo.evaluate(video => !video.paused && video.currentTime > 0), { timeout: 15000 }).toBe(true);
    expect(await heroVideo.evaluate(video => video.muted)).toBe(true);
  });
  await check('Pause control stops both motion and video', async () => {
    await page.getByRole('button', { name: 'Pause motion', exact: true }).click();
    await expect(page.locator('.wm-welcome')).toHaveAttribute('data-motion', 'off');
    expect(await heroVideo.evaluate(video => video.paused)).toBe(true);
  });
  await check('Pause preference survives assessment navigation and return', async () => {
    await page.getByRole('button', { name: 'Assessment', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-welcome-motion', 'off');
    await page.getByRole('button', { name: 'Enable animations', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-welcome-motion', 'on');
    await page.getByRole('button', { name: 'Pause animations', exact: true }).click();
    await expect(page.locator('html')).toHaveAttribute('data-welcome-motion', 'off');
    await page.getByRole('button', { name: 'Overview', exact: true }).click();
    await expect(page.getByRole('button', { name: 'Play motion', exact: true })).toBeVisible();
    await expect(page.locator('.wm-welcome')).toHaveAttribute('data-motion', 'off');
    expect(await heroVideo.evaluate(video => video.paused && !video.hasAttribute('src'))).toBe(true);
  });
  await check('Play control resumes background video', async () => {
    await page.getByRole('button', { name: 'Play motion', exact: true }).click();
    await expect.poll(() => heroVideo.evaluate(video => !video.paused)).toBe(true);
  });
  await check('Background scene selectors change scene and stop hidden video', async () => {
    await page.getByRole('button', { name: '02 In conversation', exact: true }).click();
    await expect(page.locator('.wm-still.is-active')).toHaveAttribute('src', '/images/care.jpg');
    expect(await heroVideo.evaluate(video => video.paused)).toBe(true);
    await page.getByRole('button', { name: '03 At ease', exact: true }).click();
    await expect(page.locator('.wm-still.is-active')).toHaveAttribute('src', '/images/calm.jpg');
    await page.getByRole('button', { name: '01 In motion', exact: true }).click();
    await expect.poll(() => heroVideo.evaluate(video => !video.paused)).toBe(true);
  });
  await page.screenshot({ path: 'qa/screenshots/motion-hero-desktop.png', fullPage: false });
  await check('Scrolling visibly changes hero depth and page progress', async () => {
    await scrollTo(0);
    const media = page.locator('.wm-hero-media');
    const progress = page.locator('.wm-scroll-track > div');
    const before = await visualTransform(media);
    const progressBefore = await visualTransform(progress);
    await scrollTo(350);
    await expect.poll(() => visualTransform(media)).not.toBe(before);
    await expect.poll(() => visualTransform(progress)).not.toBe(progressBefore);
    await scrollTo(0);
  });
  await check('Algorithmic contours respond to pointer movement without intercepting controls', async () => {
    const workflow = page.locator('.wm-workflow');
    await workflow.scrollIntoViewIfNeeded();
    const box = await workflow.boundingBox();
    const contours = page.locator('.wm-contour-lines');
    await page.mouse.move(box.x + box.width * .25, box.y + box.height * .4);
    const before = await visualTransform(contours);
    await page.mouse.move(box.x + box.width * .8, box.y + box.height * .7);
    await expect.poll(() => visualTransform(contours)).not.toBe(before);
    await expect(page.locator('.wm-contour-field')).toHaveAttribute('aria-hidden', 'true');
    expect(await page.locator('.wm-contour-field').evaluate(element => getComputedStyle(element).pointerEvents)).toBe('none');
    await page.getByRole('tab', { name: '02 Make it yours', exact: true }).click();
    await expect(page.getByRole('heading', { name: 'Every detail deserves a second look.' })).toBeVisible();
  });
  await check('Workflow tabs support arrows, Home, End, and selection', async () => {
    const first = page.getByRole('tab', { name: '01 Bring your details', exact: true });
    await first.scrollIntoViewIfNeeded(); await first.focus();
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('tab', { name: '02 Make it yours', exact: true })).toBeFocused();
    await expect(page.getByRole('heading', { name: 'Every detail deserves a second look.' })).toBeVisible();
    await page.keyboard.press('End');
    await expect(page.getByRole('tab', { name: '03 Explore the picture', exact: true })).toHaveAttribute('aria-selected', 'true');
    await page.keyboard.press('Home');
    await expect(first).toBeFocused();
  });
  await check('Background video pauses when its hero leaves the viewport', async () => {
    await page.locator('.wm-perspectives').scrollIntoViewIfNeeded();
    await expect.poll(() => heroVideo.evaluate(video => video.paused)).toBe(true);
  });
  await check('Photo tabs, keyboard, previous and next controls work', async () => {
    await page.getByRole('tab', { name: 'Movement', exact: true }).focus();
    await page.keyboard.press('ArrowRight');
    await expect(page.getByRole('tab', { name: 'Rest & recovery', exact: true })).toBeFocused();
    await expect(page.locator('.wm-perspective-image > img')).toHaveAttribute('src', '/images/calm.jpg');
    await page.getByRole('button', { name: 'Next perspective' }).click();
    await expect(page.locator('.wm-perspective-image > img')).toHaveAttribute('src', '/images/care.jpg');
    await page.getByRole('button', { name: 'Previous perspective' }).click();
    await expect(page.locator('.wm-perspective-image > img')).toHaveAttribute('src', '/images/calm.jpg');
  });
  await check('Photo lightbox opens and Escape restores trigger focus', async () => {
    const trigger = page.getByRole('button', { name: 'Enlarge rest & recovery photograph' });
    const bounds = await trigger.boundingBox();
    expect(bounds.width).toBeGreaterThanOrEqual(44);
    expect(bounds.height).toBeGreaterThanOrEqual(44);
    await trigger.click();
    await expect(page.getByRole('dialog', { name: 'Rest & recovery photograph' })).toBeVisible();
    await expect(page.getByRole('button', { name: 'Close photograph' })).toBeFocused();
    await page.keyboard.press('Escape');
    await expect(page.getByRole('dialog', { name: 'Rest & recovery photograph' })).not.toBeVisible();
    await expect(trigger).toBeFocused();
  });
  await check('Changing content while motion paused remains fully visible', async () => {
    await page.getByRole('button', { name: 'Pause motion', exact: true }).click();
    await page.getByRole('tab', { name: '02 Make it yours', exact: true }).click();
    await expect.poll(() => page.locator('.wm-chapter-panel').evaluate(element => Number(getComputedStyle(element).opacity))).toBe(1);
    await page.getByRole('tab', { name: 'Conversation', exact: true }).click();
    await expect.poll(() => page.locator('.wm-perspective-copy').evaluate(element => Number(getComputedStyle(element).opacity))).toBe(1);
  });
  await check('Paused motion resets transforms and ignores further scrolling and pointer movement', async () => {
    const media = page.locator('.wm-hero-media');
    const contours = page.locator('.wm-contour-lines');
    const before = await visualTransform(media);
    const contoursBefore = await visualTransform(contours);
    await scrollTo(400);
    await page.mouse.move(1200, 650);
    await page.evaluate(() => new Promise(resolve => requestAnimationFrame(() => requestAnimationFrame(resolve))));
    expect(await visualTransform(media)).toBe(before);
    expect(await visualTransform(contours)).toBe(contoursBefore);
    expect(await page.locator('.wm-welcome').evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === 'running').length)).toBe(0);
  });
  await check('Changing reduced-motion preference stops motion immediately and respects manual pause', async () => {
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(page.getByRole('button', { name: 'Reduced motion enabled', exact: true })).toBeDisabled();
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await expect(page.getByRole('button', { name: 'Play motion', exact: true })).toBeVisible();
    await expect(page.locator('html')).toHaveAttribute('data-welcome-motion', 'off');
    await page.getByRole('button', { name: 'Play motion', exact: true }).click();
    await expect.poll(() => heroVideo.evaluate(video => !video.paused)).toBe(true);
    await page.emulateMedia({ reducedMotion: 'reduce' });
    await expect(page.locator('html')).toHaveAttribute('data-welcome-motion', 'off');
    await expect.poll(() => heroVideo.evaluate(video => video.paused)).toBe(true);
    expect(await page.locator('.wm-welcome').evaluate(element => element.getAnimations({ subtree: true }).filter(animation => animation.playState === 'running').length)).toBe(0);
    const lines = await page.locator('.wm-kinetic-line').evaluateAll(elements => elements.map(element => ({ opacity: getComputedStyle(element).opacity, animation: getComputedStyle(element).animationName })));
    expect(lines.length).toBeGreaterThan(0);
    expect(lines.every(line => line.opacity === '1' && line.animation === 'none')).toBe(true);
    await page.emulateMedia({ reducedMotion: 'no-preference' });
    await expect(page.getByRole('button', { name: 'Pause motion', exact: true })).toBeVisible();
    await page.getByRole('button', { name: 'Pause motion', exact: true }).click();
  });
  for (const width of [320, 390, 768, 1440]) {
    await check(`${width}px layout has no horizontal overflow`, async () => {
      await page.setViewportSize({ width, height: width < 500 ? 844 : 1000 });
      await page.evaluate(() => scrollTo(0, 0));
      expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
      const cta = await page.getByRole('button', { name: 'Start assessment', exact: true }).boundingBox();
      const bottom = await page.locator('.wm-hero-bottom').boundingBox();
      expect(cta.y + cta.height).toBeLessThan(bottom.y);
      await page.screenshot({ path: `qa/screenshots/motion-${width}.png`, fullPage: true });
    });
  }
  const reducedContext = await browser.newContext({ viewport: { width: 390, height: 844 }, reducedMotion: 'reduce' });
  reducedContext.on('request', trackRequests);
  const reduced = await reducedContext.newPage();
  const reducedRequests = [];
  reduced.on('request', request => { if (request.url().includes('.mp4')) reducedRequests.push(request.url()); });
  await check('Reduced motion never loads MP4 media and disables continuous motion', async () => {
    await reduced.goto('http://127.0.0.1:5175/');
    await reduced.locator('.wm-perspectives').scrollIntoViewIfNeeded();
    await expect(reduced.getByRole('button', { name: 'Reduced motion enabled', exact: true })).toBeDisabled();
    await expect(reduced.locator('.wm-welcome')).toHaveAttribute('data-motion', 'off');
    expect(reducedRequests).toEqual([]);
    expect(await reduced.locator('.wm-welcome video').evaluateAll(videos => videos.every(video => !video.hasAttribute('src')))).toBe(true);
  });
  await reducedContext.close();
  await check('Welcome page no longer renders or loads the decorative heart', async () => {
    await expect(page.locator('.wm-heart-art, video[src*="heart-loop"], img[src*="heart-poster"]')).toHaveCount(0);
    expect(mediaRequests.some(url => url.includes('heart-loop'))).toBe(false);
  });
  await check('All frontend requests stay local and no backend requests occur', async () => {
    expect(unexpectedRequests).toEqual([]);
  });
  expect(errors).toEqual([]);
  await writeFile('qa/motion-results.json', JSON.stringify({ checks, failures, errors, mediaRequests, unexpectedRequests }, null, 2));
  console.log(JSON.stringify({ passed: checks.length, failed: failures.length, errors }, null, 2));
} finally { await browser.close(); }
if (failures.length) process.exitCode = 1;
