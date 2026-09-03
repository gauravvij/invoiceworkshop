import { expect, test } from '@playwright/test';

test('the draw schedule computes the columns a reviewer checks', async ({ page }) => {
  await page.goto('/progress-draw-schedule/');
  await page.getByLabel('Scheduled value, line 1').fill('200000.00');
  await page.getByLabel('Previous, line 1').fill('60000.00');
  await page.getByLabel('This period, line 1').fill('40000.00');
  await page.getByLabel('Less previous certificates').fill('54000.00');
  await page.getByLabel('This period, line 1').blur();

  const summary = page.locator('.draw-summary');
  await expect(summary).toContainText('$100,000.00');   // total completed
  await expect(summary).toContainText('$10,000.00');    // retainage at 10%
  await expect(summary).toContainText('$90,000.00');    // earned less retainage
  await expect(page.locator('.draw-summary-total')).toContainText('$36,000.00');
});

test('the retainage reduction is judged on the contract, not on one line', async ({ page }) => {
  await page.goto('/progress-draw-schedule/');
  await page.getByLabel('Reduce retainage after 50% complete').check();
  // Line one finished, line two untouched: the job is a quarter complete, so
  // full retainage still applies even though a line is done.
  await page.getByLabel('Scheduled value, line 1').fill('100.00');
  await page.getByLabel('Previous, line 1').fill('100.00');
  await page.getByLabel('Scheduled value, line 2').fill('300.00');
  await page.getByLabel('Scheduled value, line 2').blur();
  await expect(page.locator('.draw-tool')).toContainText('Currently applying 10.0%');

  await page.getByLabel('Previous, line 2').fill('300.00');
  await page.getByLabel('Previous, line 2').blur();
  await expect(page.locator('.draw-tool')).toContainText('Currently applying 5.0%');
});

test('an over-billed line is shown rather than hidden', async ({ page }) => {
  await page.goto('/progress-draw-schedule/');
  await page.getByLabel('Scheduled value, line 1').fill('100.00');
  await page.getByLabel('Previous, line 1').fill('120.00');
  await page.getByLabel('Previous, line 1').blur();
  await expect(page.locator('.draw-table td.over-billed').first()).toBeVisible();
});

test('the schedule survives a reload and never leaves the browser', async ({ page }) => {
  const posted: string[] = [];
  page.on('request', (request) => {
    if (['POST', 'PUT', 'PATCH'].includes(request.method())) posted.push(request.url());
  });
  await page.goto('/progress-draw-schedule/');
  await page.getByLabel('Project').fill('Maple Street fit-out');
  await page.getByLabel('Scheduled value, line 1').fill('12345.00');
  await page.getByLabel('Scheduled value, line 1').blur();
  await page.reload();
  await expect(page.getByLabel('Project')).toHaveValue('Maple Street fit-out');
  await expect(page.getByLabel('Scheduled value, line 1')).toHaveValue('12345.00');
  expect(posted).toEqual([]);
});
