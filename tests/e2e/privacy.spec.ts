import { expect, test } from '@playwright/test';

test('production analytics never receive document or customer contents', async ({ page }) => {
  test.skip(!process.env.PLAYWRIGHT_BASE_URL, 'Production analytics are enabled only in the deployed build');

  const requests: string[] = [];
  page.on('request', (request) => {
    requests.push(`${request.method()} ${request.url()} ${request.postData() ?? ''}`);
  });

  const sensitiveValues = [
    'Canary Workshop 8ZQ4',
    'Canary Customer 4KJ9',
    'canary-private@example.com',
    '91 Canary Privacy Lane',
    'TAX-CANARY-771',
    'Private consulting line 992',
    'BANK-CANARY-551',
    'NOTE-CANARY-337',
  ];

  await page.goto('/');
  await page.getByLabel('Business name').fill(sensitiveValues[0]);
  await page.getByLabel('Email').first().fill(sensitiveValues[2]);
  await page.getByLabel('Street address').first().fill(sensitiveValues[3]);
  await page.getByLabel('Tax / business ID').fill(sensitiveValues[4]);
  await page.getByRole('textbox', { name: 'Name', exact: true }).fill(sensitiveValues[1]);
  await page.getByLabel('Description').fill(sensitiveValues[5]);
  await page.getByRole('textbox', { name: /Unit price/ }).fill('9876.54');
  await page.getByLabel('Payment instructions').fill(sensitiveValues[6]);
  await page.getByLabel('Notes').fill(sensitiveValues[7]);
  await page.getByRole('button', { name: 'Save now' }).click();
  await page.getByRole('button', { name: 'Duplicate' }).click();
  const download = page.waitForEvent('download');
  await page.getByRole('button', { name: 'Download PDF' }).click();
  await download;
  await page.getByLabel('Convert this document').selectOption('receipt');
  await page.getByRole('button', { name: 'Convert' }).click();
  await page.reload();
  await page.waitForTimeout(3_000);

  const transcript = requests.join('\n');
  for (const value of sensitiveValues) {
    expect(transcript.toLowerCase()).not.toContain(value.toLowerCase());
    expect(transcript.toLowerCase()).not.toContain(encodeURIComponent(value).toLowerCase());
  }

  const thirdPartyHosts = new Set(
    requests
      .map((entry) => entry.match(/https?:\/\/([^/\s]+)/)?.[1])
      .filter((host): host is string => Boolean(host) && host !== 'invoiceworkshop.com'),
  );
  for (const host of thirdPartyHosts) {
    expect(
      host === 'www.googletagmanager.com'
        || host.endsWith('.google-analytics.com')
        || host === 'www.google-analytics.com'
        || host === 'static.cloudflareinsights.com',
      `unexpected third-party request to ${host}`,
    ).toBe(true);
  }

  expect(transcript).toContain('tool_started');
  expect(transcript).toContain('document_saved');
  expect(transcript).toContain('document_duplicated');
  expect(transcript).toContain('pdf_downloaded');
  expect(transcript).toContain('document_converted');
  expect(transcript).toContain('returning_workspace_loaded');
});
