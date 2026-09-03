import { expect, test } from '@playwright/test';
import { mkdir, stat } from 'node:fs/promises';
import path from 'node:path';

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
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Saved Mobile Customer');
  await page.getByLabel('Description').fill('Mobile service');
  await page.getByRole('textbox', { name: /Unit price/ }).fill('125.00');
  await page.getByRole('button', { name: '+ Add line item' }).click();
  await page.getByLabel('Description').nth(1).fill('Second mobile item');
  await expect(page.getByText('Saved locally on this device.')).toBeVisible({ timeout: 5_000 });
  await page.getByRole('button', { name: 'Show preview' }).click();
  await expect(page.getByLabel('Live document preview')).toBeVisible();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download PDF' }).click();
  expect((await download).suggestedFilename()).toMatch(/^invoice-INV-/);
  await page.getByRole('button', { name: 'Show editor' }).click();
  await expect(page.getByLabel('Business name')).toBeVisible();
  await page.reload();
  await expect(page.getByLabel('Business name')).toHaveValue('Mobile Co.');
  const savedContacts = page.getByLabel('Saved contacts');
  await expect(savedContacts.getByRole('option', { name: 'Saved Mobile Customer' })).toHaveCount(1);
  await savedContacts.selectOption({ label: 'Saved Mobile Customer' });
  const before = await page.getByLabel('Document number').inputValue();
  await page.getByRole('button', { name: 'Duplicate' }).click();
  await expect(page.getByLabel('Document number')).not.toHaveValue(before);
});

test('upgrades a legacy database without losing the saved business', async ({ page }) => {
  await page.goto('/about/');
  await page.evaluate(async () => {
    await new Promise<void>((resolve, reject) => {
      const remove = indexedDB.deleteDatabase('invoice-workshop');
      remove.onsuccess = () => resolve();
      remove.onerror = () => reject(remove.error);
    });
    await new Promise<void>((resolve, reject) => {
      const open = indexedDB.open('invoice-workshop', 1);
      open.onupgradeneeded = () => {
        for (const name of ['profiles', 'clients', 'catalog', 'documents', 'settings']) {
          if (!open.result.objectStoreNames.contains(name)) open.result.createObjectStore(name, { keyPath: 'id' });
        }
        open.transaction?.objectStore('profiles').put({ id: 'default-business', name: 'Legacy Builders', address: null });
        open.transaction?.objectStore('documents').put({ id: 'malformed-document', kind: 'not-a-document' });
      };
      open.onsuccess = () => {
        open.result.close();
        resolve();
      };
      open.onerror = () => reject(open.error);
    });
  });

  await page.goto('/');
  await expect(page.getByLabel('Business name')).toHaveValue('Legacy Builders');
  const schema = await page.evaluate(async () => new Promise<{ version: number; marker: number | undefined }>((resolve, reject) => {
    const open = indexedDB.open('invoice-workshop');
    open.onsuccess = () => {
      const database = open.result;
      const request = database.transaction('settings').objectStore('settings').get('schema');
      request.onsuccess = () => {
        resolve({ version: database.version, marker: request.result?.version });
        database.close();
      };
      request.onerror = () => reject(request.error);
    };
    open.onerror = () => reject(open.error);
  }));
  expect(schema).toEqual({ version: 2, marker: 2 });
});

test('print output contains the customer document without site branding', async ({ page }) => {
  await page.goto('/');
  await page.getByLabel('Business name').fill('Print Test Company');
  await page.emulateMedia({ media: 'print' });
  await expect(page.locator('.document-preview')).toBeVisible();
  await expect(page.locator('.site-header')).toBeHidden();
  await expect(page.locator('.site-footer')).toBeHidden();
  await expect(page.locator('.document-preview')).not.toContainText('InvoiceWorkshop');
});

test('creates a realistic branded multi-page customer PDF', async ({ page, browserName }) => {
  test.skip(browserName !== 'chromium', 'One deterministic artifact is sufficient for manual PDF inspection');

  await page.setContent(`
    <div id="qa-logo" style="width:480px;height:120px;display:flex;align-items:center;gap:24px;padding:18px;background:white;color:#17324d;font:700 32px Arial">
      <span style="display:grid;place-items:center;width:78px;height:78px;border-radius:20px;background:#107166;color:white">N</span>
      <span>NORTHSTAR WORKS</span>
    </div>
  `);
  const logo = await page.locator('#qa-logo').screenshot();

  await page.goto('/');
  await page.getByLabel('Business name').fill('Northstar Construction and Professional Services Incorporated');
  await page.getByLabel('Email').first().fill('billing@northstar.example');
  await page.getByLabel('Phone').first().fill('+1 212 555 0199');
  await page.getByLabel('Tax / business ID').fill('US-TEST-883102');
  await page.getByLabel('Street address').first().fill('1847 Long Harbor Industrial Boulevard');
  await page.getByLabel('City').first().fill('Brooklyn');
  await page.getByLabel('State / region').first().fill('New York');
  await page.getByLabel('Postal code').first().fill('11201');
  await page.locator('input[type="file"]').setInputFiles({ name: 'northstar-logo.png', mimeType: 'image/png', buffer: logo });
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill('Harbor Point Development Partners LLC');
  await page.getByLabel('Email').nth(1).fill('accounts@harborpoint.example');
  await page.getByLabel('Street address').nth(1).fill('500 Waterfront Plaza, Suite 1200');
  await page.getByLabel('City').nth(1).fill('New York');
  await page.getByLabel('State / region').nth(1).fill('New York');
  await page.getByLabel('Postal code').nth(1).fill('10004');

  const longDescription = 'Project management, field coordination, material scheduling, progress documentation, and detailed closeout support for the waterfront renovation phase';
  await page.getByLabel('Description').fill(longDescription);
  await page.getByLabel('Quantity').fill('18.5');
  await page.getByRole('textbox', { name: /Unit price/ }).fill('145.75');
  await page.getByLabel('Discount %').fill('7.5');
  await page.getByLabel('Tax %').fill('8.875');
  for (let index = 2; index <= 14; index += 1) {
    await page.getByRole('button', { name: '+ Add line item' }).click();
    await page.getByLabel('Description').nth(index - 1).fill(`Construction service line ${index}: labor, materials, equipment coordination and site reporting`);
    await page.getByLabel('Quantity').nth(index - 1).fill(String(index + 0.25));
    await page.getByRole('textbox', { name: /Unit price/ }).nth(index - 1).fill(String(80 + index * 7.25));
    await page.getByLabel('Tax %').nth(index - 1).fill('8.875');
  }
  await page.getByLabel('Shipping').fill('185.40');
  await page.getByLabel('Adjustment (+/−)').fill('-25.00');
  await page.getByLabel('Notes').fill('Please reference the project and invoice number with all correspondence. Work was completed in coordinated phases and reviewed with the site representative.');
  await page.getByLabel('Payment instructions').fill('Pay by bank transfer using the remittance details supplied directly by Northstar Works. Do not send payment details by email.');
  await page.getByLabel('Terms').fill('Payment due within 30 days. Questions about quantities or scope should be raised promptly with the project manager. This test text is intentionally long enough to exercise wrapping and page flow.');
  await expect(page.locator('.document-preview')).not.toContainText('InvoiceWorkshop');

  const pendingDownload = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download PDF' }).click();
  const download = await pendingDownload;
  expect(download.suggestedFilename()).toMatch(/^invoice-INV-\d+\.pdf$/);
  const temporaryPath = await download.path();
  expect(temporaryPath).toBeTruthy();
  expect((await stat(temporaryPath!)).size).toBeGreaterThan(10_000);
  if (process.env.PDF_QA_OUTPUT) {
    await mkdir(process.env.PDF_QA_OUTPUT, { recursive: true });
    await download.saveAs(path.join(process.env.PDF_QA_OUTPUT, download.suggestedFilename()));
  }
});

test('a receipt records the payment rather than requesting one', async ({ page, isMobile }) => {
  await page.goto('/receipt-generator/');
  // The heading is the whole point: a receipt is not an invoice with a chip on it.
  await expect(page.locator('.document-identity h2')).toHaveText('Receipt');
  await expect(page.getByLabel('Paid date')).toBeVisible();
  await expect(page.getByLabel('Due / valid until')).toHaveCount(0);
  await expect(page.getByLabel('Payment method')).toBeVisible();
  await expect(page.getByLabel('Transaction reference')).toBeVisible();

  const rate = page.locator('.line-item').first().getByLabel('Unit price');
  await rate.fill('100.00');
  await rate.blur();
  await expect(page.locator('.preview-totals')).toContainText('Amount received');
  // Nothing was underpaid, so it marks itself paid without being asked. The
  // preview is behind a toggle at mobile width, and a mark nobody can see is
  // not a mark, so the check has to open it rather than settle for the DOM.
  const showPaidMark = async () => {
    if (isMobile) await page.getByRole('button', { name: 'Show preview' }).click();
    await expect(page.locator('.paid-mark')).toBeVisible();
    if (isMobile) await page.getByRole('button', { name: 'Show editor' }).click();
  };
  await showPaidMark();

  await page.getByLabel('Amount received').fill('40.00');
  await page.getByLabel('Amount received').blur();
  await expect(page.locator('.preview-totals')).toContainText('Balance remaining');
  await expect(page.locator('.paid-mark')).toHaveCount(0);
});
