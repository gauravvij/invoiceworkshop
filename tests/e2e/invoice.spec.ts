import { expect, test } from '@playwright/test';

test('creates, calculates, saves and restores an invoice', async ({ page }) => {
  await page.goto('/');
  await expect(page.getByRole('heading', { level: 1, name: 'Free Invoice Generator' })).toBeVisible();
  await page.getByLabel('Business name').fill('Bright Workshop LLC');
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Northwind Traders');
  await page.getByLabel('Description').fill('Design services');
  await page.getByRole('textbox', { name: /Unit price/ }).fill('125.50');
  await page.getByLabel('Tax %').fill('8.25');
  await expect(page.locator('.grand-total')).toContainText('$135.85');
  await expect(page.getByText('Saved locally on this device.')).toBeVisible({ timeout: 5_000 });
  await page.reload();
  await expect(page.getByLabel('Business name')).toHaveValue('Bright Workshop LLC');
  await expect(page.getByRole('textbox', { name: 'Name', exact: true })).toHaveValue('Northwind Traders');
  await expect(page.getByLabel('Description')).toHaveValue('Design services');
});

test('adds items, saves reusable data, duplicates and downloads a PDF', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Business name').fill('Field Notes Inc.');
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('River City Co.');
  await page.getByLabel('Description').fill('Consulting');
  await page.getByRole('textbox', { name: /Unit price/ }).fill('90.00');
  await page.getByRole('button', { name: 'Save item' }).click();
  await expect(page.getByLabel('Add a saved product or service').getByRole('option', { name: /Consulting/ })).toHaveCount(1);
  await page.getByRole('button', { name: '+ Add line item' }).click();
  await expect(page.getByText('Item 2')).toBeVisible();
  await page.getByRole('button', { name: 'Save now' }).click();
  const before = await page.getByLabel('Document number').inputValue();
  await page.getByRole('button', { name: 'Duplicate' }).click();
  await expect(page.getByLabel('Document number')).not.toHaveValue(before);
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download PDF' }).click();
  expect((await download).suggestedFilename()).toMatch(/^invoice-INV-/);
});

test('converts an estimate to a work order and then an invoice', async ({ page }) => {
  await page.goto('/estimate-generator/');
  await page.getByLabel('Business name').fill('Build Right');
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('A Customer');
  await page.getByLabel('Description').fill('Project phase one');
  await page.getByLabel('Convert this document').selectOption('workOrder');
  await page.getByRole('button', { name: 'Convert' }).click();
  await expect(page.getByLabel('Convert this document')).toBeVisible();
  await expect(page.locator('.document-identity h2')).toHaveText('Work Order');
  await expect(page.getByLabel('Document number')).toHaveValue(/^WO-/);
  await page.getByLabel('Convert this document').selectOption('invoice');
  await page.getByRole('button', { name: 'Convert' }).click();
  await expect(page.locator('.document-identity h2')).toHaveText('Invoice');
  await expect(page.getByLabel('Document number')).toHaveValue(/^INV-/);
  await expect(page.getByLabel('Description')).toHaveValue('Project phase one');
});

test('can clear all browser data', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Business name').fill('Temporary Business');
  await expect(page.getByText('Saved locally on this device.')).toBeVisible({ timeout: 5_000 });
  page.on('dialog', (dialog) => dialog.accept());
  await page.getByText('Local data controls').click();
  await page.getByRole('button', { name: 'Clear all local data' }).click();
  await page.waitForLoadState('domcontentloaded');
  await expect(page.getByLabel('Business name')).toHaveValue('');
});

test('mobile editor and preview toggle are fully usable', async ({ page, isMobile }) => {
  test.skip(!isMobile, 'Mobile-only workflow');
  await page.goto('/');
  await page.getByLabel('Business name').fill('Mobile Co.');
  await page.getByRole('button', { name: 'Show preview' }).click();
  await expect(page.getByLabel('Live document preview')).toBeVisible();
  await page.getByRole('button', { name: 'Show editor' }).click();
  await expect(page.getByLabel('Business name')).toBeVisible();
});
