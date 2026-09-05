import { expect, test } from '@playwright/test';

const publicUrls = ['/', '/proforma-invoice-generator/', '/quotation-generator/', '/work-order-generator/', '/purchase-order-generator/', '/estimate-generator/', '/construction-invoice-template/', '/contractor-invoice-template/', '/invoice-template/', '/receipt-generator/', '/credit-note-generator/', '/timesheet-invoice-generator/', '/delivery-note-template/', '/progress-draw-schedule/', '/vat-invoice-template-uk/', '/gst-invoice-format-india/', '/tax-invoice-template-australia/', '/gst-hst-invoice-template-canada/', '/research/free-invoice-generator-audit-2026/', '/about/', '/privacy/', '/terms/', '/contact/'];

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
    expect(await page.locator('meta[property="og:url"]').getAttribute('content')).toBe(canonical);
    expect(canonicals.has(canonical!), `duplicate canonical: ${canonical}`).toBe(false);
    canonicals.add(canonical!);
    expect(sitemap).toContain(`<loc>${canonical}</loc>`);
    expect(await page.locator('meta[name="robots"][content*="noindex"]').count()).toBe(0);
    expect(await page.locator('body').innerHTML()).not.toContain('localhost');
    const schemaBlocks = await page.locator('script[type="application/ld+json"]').allTextContents();
    expect(schemaBlocks.length).toBeGreaterThan(0);
    for (const block of schemaBlocks) {
      expect(() => JSON.parse(block)).not.toThrow();
      expect(block).not.toMatch(/localhost|staging|workers\.dev/);
    }
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

test('canonical pages have no broken internal links or images and are internally discoverable', async ({ page, request }) => {
  const discovered = new Set<string>();
  for (const path of publicUrls) {
    await page.goto(path);
    const expectedHost = new URL(page.url()).hostname;
    const links = await page.locator('a[href]').evaluateAll((anchors) => anchors
      .map((anchor) => new URL((anchor as HTMLAnchorElement).href))
      .filter((url) => url.origin === window.location.origin)
      .map((url) => `${url.pathname}${url.search}`));
    for (const href of links) {
      const target = new URL(href, 'https://invoiceworkshop.com').pathname;
      // A page linking to itself proves nothing about whether anything else
      // links to it, and four country pages shipped as orphans because this
      // assertion counted self-links as discovery.
      if (target !== path) discovered.add(target);
      const response = await request.get(href);
      expect(response.status(), `${path} links to ${href}`).toBeLessThan(400);
      expect(new URL(response.url()).hostname).toBe(expectedHost);
    }
    const images = await page.locator('img[src]').evaluateAll((elements) => elements.map((image) => (image as HTMLImageElement).src));
    for (const source of images) {
      const response = await request.get(source);
      expect(response.status(), `${path} loads ${source}`).toBe(200);
    }
  }
  for (const path of publicUrls.filter((path) => path !== '/')) expect(discovered.has(path), `${path} internal link`).toBe(true);
});

test('query strings do not create document-state canonicals', async ({ page }) => {
  await page.goto('/?client_name=should-not-be-indexed&total=999');
  await expect(page.locator('link[rel="canonical"]')).toHaveAttribute('href', 'https://invoiceworkshop.com/');
  await expect(page.locator('meta[property="og:url"]')).toHaveAttribute('content', 'https://invoiceworkshop.com/');
});

test('production synonym routes redirect directly to the homepage', async ({ request }) => {
  test.skip(!process.env.PLAYWRIGHT_BASE_URL, 'Worker redirects are only available in production');
  for (const path of ['/invoice-generator/', '/invoice-maker/', '/invoice-builder/', '/free-invoice-generator/', '/online-invoice-generator/']) {
    const response = await request.get(path, { maxRedirects: 0 });
    expect(response.status(), path).toBe(301);
    expect(new URL(response.headers().location!, 'https://invoiceworkshop.com').href).toBe('https://invoiceworkshop.com/');
  }
});

test('no page scrolls sideways at mobile width', async ({ page }) => {
  // Worked-example tables carry a min-width so their columns stay readable. The
  // scroll container holds that width only if the grid column around it is
  // allowed to shrink below its content; `1fr` is not, and three pages shipped
  // a sideways-scrolling document before this was caught.
  await page.setViewportSize({ width: 360, height: 780 });
  for (const path of publicUrls) {
    await page.goto(path);
    const { scrollWidth, clientWidth } = await page.evaluate(() => ({
      scrollWidth: document.documentElement.scrollWidth,
      clientWidth: document.documentElement.clientWidth,
    }));
    expect(scrollWidth, `${path} overflows: ${scrollWidth} > ${clientWidth}`)
      .toBeLessThanOrEqual(clientWidth);
  }
});
