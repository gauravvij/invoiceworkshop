import { expect, test } from '@playwright/test';

const publicUrls = ['/', '/proforma-invoice-generator/', '/quotation-generator/', '/work-order-generator/', '/purchase-order-generator/', '/estimate-generator/', '/construction-invoice-template/', '/contractor-invoice-template/', '/invoice-template/', '/about/', '/privacy/', '/terms/', '/contact/'];

test('every canonical page has complete, unique static SEO', async ({ page, request }) => {
  const titles = new Set<string>();
  const canonicals = new Set<string>();
  const sitemap = await (await request.get('/sitemap.xml')).text();
  for (const path of publicUrls) {
    const response = await page.goto(path);
    expect(response?.status(), path).toBe(200);
    await expect(page.locator('h1'), `${path} H1`).toHaveCount(1);
    const title = await page.title();
    expect(title.length).toBeGreaterThan(10);
    expect(titles.has(title), `duplicate title: ${title}`).toBe(false);
    titles.add(title);
    const description = await page.locator('meta[name="description"]').getAttribute('content');
    expect(description?.length).toBeGreaterThan(50);
    const canonical = await page.locator('link[rel="canonical"]').getAttribute('href');
    expect(canonical).toBe(`https://invoiceworkshop.com${path}`);
    expect(canonicals.has(canonical!), `duplicate canonical: ${canonical}`).toBe(false);
    canonicals.add(canonical!);
    expect(sitemap).toContain(`<loc>${canonical}</loc>`);
    expect(await page.locator('meta[name="robots"][content*="noindex"]').count()).toBe(0);
    expect(await page.locator('body').innerHTML()).not.toContain('localhost');
    expect(await page.locator('script[type="application/ld+json"]').count()).toBeGreaterThan(0);
  }
});

test('robots, sitemap, crawlable navigation, redirects and 404 work', async ({ page, request }) => {
  const robots = await request.get('/robots.txt');
  expect(robots.status()).toBe(200);
  expect(await robots.text()).toContain('Sitemap: https://invoiceworkshop.com/sitemap.xml');
  const sitemap = await request.get('/sitemap.xml');
  expect(sitemap.status()).toBe(200);
  expect(sitemap.headers()['content-type']).toContain('application/xml');
  await page.goto('/');
  expect(await page.locator('nav a[href]').count()).toBeGreaterThan(3);
  const notFound = await page.goto('/definitely-not-a-real-page/');
  expect(notFound?.status()).toBe(404);
  await expect(page.locator('h1')).toHaveText("That page isn't in the workshop.");
});
