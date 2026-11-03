import { chromium, expect } from '@playwright/test';
import { mkdir, writeFile } from 'node:fs/promises';

const browser = await chromium.launch({ headless: true });
const page = await browser.newPage({ viewport: { width: 1440, height: 1050 }, reducedMotion: 'reduce' });
const apiRequests = [];
const consoleErrors = [];
const checks = [];
page.on('request', request => { if (new URL(request.url()).pathname.startsWith('/api/')) apiRequests.push(request.url()); });
page.on('pageerror', error => consoleErrors.push(error.message));
const file = (name, text, mimeType = 'text/plain') => ({ name, mimeType, buffer: Buffer.from(text) });
const report = data => page.getByLabel('Select laboratory report').setInputFiles(data);
const ecg = data => page.getByLabel('Select ECG waveform').setInputFiles(data);
const details = () => page.getByRole('tab', { name: 'Enter details' }).click();
const uploads = () => page.getByRole('tab', { name: 'Upload reports' }).click();
const review = () => page.locator('.inp-footer button').click();
const mark = title => { checks.push(title); console.log(`PASS ${title}`); };

try {
  await page.goto('http://127.0.0.1:5174');
  await page.getByRole('button', { name: 'Start assessment', exact: true }).click();
  await details();
  const emptyFields = await page.locator('.inp-field input, .inp-field select').evaluateAll(elements => elements.every(element => element.value === ''));
  expect(emptyFields).toBe(true);
  mark('Personal forms start completely empty');

  await page.locator('#inp-age').fill('17');
  await expect(page.locator('#inp-age')).toHaveAttribute('aria-invalid', 'true');
  await review();
  await expect(page.getByRole('tab', { name: 'Enter details' })).toBeVisible();
  await expect(page.locator('#inp-age')).toBeFocused();
  await page.locator('#inp-age').fill('46');
  await page.locator('#inp-systolic_bp').fill('116');
  await page.locator('#inp-diastolic_bp').fill('120');
  await review();
  await expect(page.getByText('Must be lower than systolic pressure.', { exact: true })).toBeVisible();
  await page.locator('#inp-diastolic_bp').fill('72');
  mark('Range and cross-field validation block review');

  await review();
  await expect(page.locator('#review-age')).toHaveValue('46');
  await page.getByRole('button', { name: 'Back to details' }).click();
  await details();
  await expect(page.locator('#inp-age')).toHaveValue('46');
  await expect(page.locator('#inp-diastolic_bp')).toHaveValue('72');
  mark('Manual entries survive review and back navigation');

  await uploads();
  await report(file('labs.json', JSON.stringify({ age: 44, sex: 'male', hdl: 55 }), 'application/json'));
  await expect(page.getByText(/3 values read locally from labs.json/)).toBeVisible();
  await details();
  await expect(page.locator('#inp-age')).toHaveValue('44');
  await expect(page.locator('#inp-sex')).toHaveValue('male');
  await expect(page.locator('#inp-hdl')).toHaveValue('55');
  await expect(page.locator('.inp-field').filter({ has: page.locator('#inp-hdl') }).getByText('Extracted', { exact: true })).toBeVisible();
  await page.locator('#inp-hdl').fill('57');
  await page.locator('#inp-hdl').fill('58');
  await expect(page.locator('.inp-field').filter({ has: page.locator('#inp-hdl') }).getByText('Corrected', { exact: true })).toBeVisible();
  mark('JSON values import and repeated edits retain Corrected provenance');

  await uploads();
  await report(file('replacement.csv', 'age,systolic_bp,diastolic_bp\n49,125,80', 'text/csv'));
  await expect(page.getByText(/3 values read locally from replacement.csv/)).toBeVisible();
  await expect(page.getByText('replacement.csv', { exact: true })).toBeVisible();
  await details();
  await expect(page.locator('#inp-age')).toHaveValue('49');
  await expect(page.locator('#inp-systolic_bp')).toHaveValue('125');
  await expect(page.locator('#inp-hdl')).toHaveValue('58');
  await uploads();
  await page.getByRole('button', { name: 'Remove report', exact: true }).click();
  await expect(page.getByText('Drop your report here')).toBeVisible();
  await details();
  await expect(page.locator('#inp-age')).toHaveValue('49');
  mark('CSV replacement imports matching fields and file removal preserves entries');

  await uploads();
  await report(file('malformed.csv', 'age,sex\n45,male\n46,female', 'text/csv'));
  await expect(page.getByText('Use a CSV with a header and exactly one data row.')).toBeVisible();
  await review();
  await expect(page.getByRole('tab', { name: 'Upload reports' })).toBeVisible();
  await page.locator('.inp-upload-error button').click();
  await expect(page.locator('.inp-upload-error')).toHaveCount(0);
  await report(file('wrong.exe', 'not a report'));
  await expect(page.getByText(/Unsupported file type/)).toBeVisible();
  await page.getByRole('button', { name: 'Dismiss', exact: true }).click();
  mark('Malformed report errors block review and can be dismissed');

  await report(file('scan.pdf', '%PDF-1.4\nlocal staged test', 'application/pdf'));
  await expect(page.getByText(/PDF and image extraction is unavailable/)).toBeVisible();
  await expect(page.getByText('scan.pdf', { exact: true })).toBeVisible();
  await page.getByRole('button', { name: /enter their values manually/i }).click();
  await expect(page.locator('#inp-age')).toHaveValue('49');
  mark('PDF is staged honestly and manual entry action works');

  await uploads();
  await ecg(file('record.dat', 'raw waveform data'));
  await expect(page.getByText('Add the matching .hea companion file.')).toBeVisible();
  await review();
  await expect(page.getByRole('tab', { name: 'Upload reports' })).toBeVisible();
  await page.locator('#inp-companion').setInputFiles(file('different.hea', 'header'));
  await expect(page.getByText('Both WFDB filenames must match before the extension.')).toBeVisible();
  await review();
  await expect(page.getByRole('tab', { name: 'Upload reports' })).toBeVisible();
  await page.locator('#inp-companion').setInputFiles(file('record.hea', 'header'));
  await expect(page.getByText('Matching file pair selected.')).toBeVisible();
  mark('WFDB missing/mismatched companions block review; matching pair is accepted');

  await ecg(file('lead-i.csv', 'I\n0.1\n0.4\n-0.3\n0.1', 'text/csv'));
  await expect(page.getByText(/1-lead waveform loaded · 4 samples per lead/)).toBeVisible();
  await expect(page.locator('#inp-sample-rate')).toHaveValue('500');
  await page.locator('#inp-sample-rate').fill('99');
  await review();
  await expect(page.getByText('Enter a whole-number sampling rate of at least 100 Hz.')).toBeVisible();
  await page.locator('#inp-sample-rate').fill('500.5');
  await review();
  await expect(page.getByRole('tab', { name: 'Upload reports' })).toBeVisible();
  await page.locator('#inp-sample-rate').fill('250');
  await review();
  await page.getByRole('button', { name: 'Back to details' }).click();
  await expect(page.locator('#inp-sample-rate')).toHaveValue('250');
  await expect(page.getByText(/1-lead waveform loaded · 4 samples per lead/)).toBeVisible();
  await expect(page.getByText('scan.pdf', { exact: true })).toBeVisible();
  mark('ECG CSV uses actual data, validates sampling rate, and survives navigation');

  await mkdir('qa/screenshots', { recursive: true });
  await page.screenshot({ path: 'qa/screenshots/inputs-desktop.png', fullPage: true });
  await page.setViewportSize({ width: 390, height: 844 });
  await page.screenshot({ path: 'qa/screenshots/inputs-mobile.png', fullPage: true });
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await details();
  expect(await page.evaluate(() => document.documentElement.scrollWidth <= innerWidth)).toBe(true);
  await page.screenshot({ path: 'qa/screenshots/fields-mobile.png', fullPage: true });
  mark('390px upload and manual layouts have no horizontal overflow');

  await page.getByRole('tab', { name: 'Enter details' }).focus();
  await page.keyboard.press('ArrowLeft');
  await expect(page.getByRole('tab', { name: 'Upload reports' })).toBeFocused();
  await expect(page.getByRole('tab', { name: 'Upload reports' })).toHaveAttribute('aria-selected', 'true');
  mark('Keyboard arrow navigation switches and focuses input tabs');
  expect(apiRequests).toEqual([]);
  expect(consoleErrors).toEqual([]);
  mark('No /api requests or browser runtime errors');
  await writeFile('qa/input-results.json', JSON.stringify({ passed: checks, apiRequests, consoleErrors }, null, 2));
} catch (error) {
  await mkdir('qa/screenshots', { recursive: true });
  await page.screenshot({ path: 'qa/screenshots/inputs-failure.png', fullPage: true });
  throw error;
} finally {
  await browser.close();
}
