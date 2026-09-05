/**
 * One tool, one fresh browser, one question: does what you type leave the page?
 *
 * Everything here is an observation of a public tool used the way a visitor
 * uses it. Nothing is typed into it but canary strings and a .invalid address,
 * no account is created, and no measurement is inferred -- a field that could
 * not be read is reported as unmeasured rather than guessed at.
 *
 * Each field gets its own canary. Knowing that *something* left the page is not
 * enough to say anything fair about a tool: an email address typed into a
 * newsletter box and a customer's address typed into an invoice line are not
 * the same finding, and the first must never be published as the second.
 *
 * Usage: node scripts/audit_measure.cjs <url> <outDir> <canary>
 */
const { chromium } = require('@playwright/test');
const fs = require('fs');
const path = require('path');

const [, , URL_ARG, OUT_DIR, CANARY] = process.argv;
if (!URL_ARG || !OUT_DIR || !CANARY) {
  console.error('usage: audit_measure.cjs <url> <outDir> <canary>');
  process.exit(2);
}

const WALL = /(sign\s?up|create an account|log in to (continue|download)|register to (continue|download)|start (your )?free trial|enter your email to (get|download|receive))/i;

const AD_TRACKER = [
  'doubleclick.net', 'googlesyndication.com', 'googletagmanager.com', 'google-analytics.com',
  'googleadservices.com', 'adservice.google.com', 'facebook.net', 'facebook.com/tr',
  'hotjar.com', 'clarity.ms', 'segment.com', 'segment.io', 'mixpanel.com', 'amplitude.com',
  'fullstory.com', 'intercom.io', 'hubspot.com', 'hs-scripts.com', 'taboola.com',
  'outbrain.com', 'criteo.com', 'bing.com/bat', 'clarity.microsoft.com', 'adroll.com',
  'linkedin.com/px', 'snap.licdn.com', 'tiktok.com', 'yandex.ru', 'matomo',
  'plausible.io', 'posthog.com', 'heap.io', 'crazyegg.com', 'quantserve.com',
];

const { registrable, sameSite } = require('./audit_domain.cjs');

(async () => {
  const evidence = {
    url: URL_ARG, measured_at: new Date().toISOString(), canary: CANARY,
    reachable: false, final_url: null, http_status: null, page_title: null,
    fillable_fields: 0, fields_filled: 0, field_map: [], action_clicked: null,
    canary_left_the_browser: null,          // true / false / null = unmeasured
    canary_left_to_third_party: null,
    canary_destinations: [], leaked_fields: [],
    third_party_domains: [], ad_tracker_domains: [],
    pdf_downloaded: false, download_name: null,
    signup_wall_text: null, login_form_present: null,
    notes: [],
  };

  let browser;
  try {
    browser = await chromium.launch({ headless: false });
    const ctx = await browser.newContext({
      viewport: { width: 1366, height: 900 },
      acceptDownloads: true,
      userAgent: 'Mozilla/5.0 (X11; Linux x86_64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/128.0.0.0 Safari/537.36',
    });
    const page = await ctx.newPage();

    const requests = [];
    page.on('request', (r) => {
      let body = null;
      try { body = r.postData(); } catch { /* multipart bodies can be unreadable */ }
      requests.push({ method: r.method(), url: r.url(), body: body ? body.slice(0, 60000) : null });
    });
    page.on('download', async (d) => {
      evidence.pdf_downloaded = true;
      evidence.download_name = d.suggestedFilename();
      try { await d.saveAs(path.join(OUT_DIR, 'download-' + d.suggestedFilename())); } catch { }
    });

    const response = await page.goto(URL_ARG, { waitUntil: 'domcontentloaded', timeout: 45000 });
    evidence.http_status = response ? response.status() : null;
    evidence.reachable = true;
    await page.waitForTimeout(4500);

    let text = '';
    for (let attempt = 0; attempt < 3; attempt++) {
      try { text = await page.evaluate(() => (document.body ? document.body.innerText : '')); break; }
      catch { evidence.notes.push('retrying after navigation during page read'); await page.waitForTimeout(4000); }
    }
    evidence.final_url = page.url();
    evidence.page_title = await page.title().catch(() => null);
    const wall = text.match(WALL);
    evidence.signup_wall_text = wall ? wall[0] : null;

    const beforeTyping = requests.length;

    const FILL = (canary) => {
      const visible = (el) => {
        const r = el.getBoundingClientRect();
        const s = getComputedStyle(el);
        return r.width > 20 && r.height > 8 && s.visibility !== 'hidden' && s.display !== 'none'
          && !el.disabled && !el.readOnly;
      };
      const nodes = [...document.querySelectorAll('input, textarea, [contenteditable="true"]')]
        .filter((el) => {
          if (el.tagName === 'INPUT') {
            const t = (el.type || 'text').toLowerCase();
            if (!['text', 'email', 'tel', 'number', 'search', 'url', ''].includes(t)) return false;
          }
          return visible(el);
        });
      const map = [];
      let n = 0;
      for (const el of nodes.slice(0, 30)) {
        const type = (el.type || el.tagName).toLowerCase();
        const token = canary + 'F' + (window.__auditIndex = (window.__auditIndex || 0) + 1);
        const value = type === 'email' ? token.toLowerCase() + '@example.invalid'
          : type === 'number' ? '7' : token;
        if (type === 'number') continue;   // a number field cannot carry a canary
        if (el.isContentEditable) { el.textContent = value; }
        else {
          const proto = el.tagName === 'TEXTAREA' ? HTMLTextAreaElement : HTMLInputElement;
          Object.getOwnPropertyDescriptor(proto.prototype, 'value').set.call(el, value);
        }
        el.dispatchEvent(new Event('input', { bubbles: true }));
        el.dispatchEvent(new Event('change', { bubbles: true }));
        el.dispatchEvent(new Event('blur', { bubbles: true }));
        map.push({
          token, type,
          name: el.name || '', id: el.id || '',
          placeholder: el.placeholder || '',
          label: (el.getAttribute('aria-label') || (el.labels && el.labels[0] ? el.labels[0].innerText : '') || '').slice(0, 60).trim(),
        });
        n++;
      }
      return { candidates: nodes.length, filled: n, map };
    };

    const fillEverywhere = async () => {
      let candidates = 0, n = 0, map = [];
      for (const f of page.frames()) {
        try {
          const r = await f.evaluate(FILL, CANARY);
          candidates += r.candidates; n += r.filled; map = map.concat(r.map);
        } catch { /* a frame that will not evaluate is not a measurement */ }
      }
      return { candidates, filled: n, map };
    };

    let filled = await fillEverywhere();

    if (filled.filled === 0) {
      // Some editors render below the fold or only once scrolled into view.
      await page.evaluate(async () => {
        for (let y = 0; y < 4; y++) { window.scrollBy(0, window.innerHeight); await new Promise((r) => setTimeout(r, 700)); }
        window.scrollTo(0, 0);
      }).catch(() => { });
      await page.waitForTimeout(2500);
      filled = await fillEverywhere();
      if (filled.filled > 0) evidence.notes.push('editor appeared only after scrolling');
    }

    if (filled.filled === 0) {
      const ENTRY = /^(create( an)?( new)?( free)?( invoice)?|start|new invoice|make (an )?invoice|get started|try it|open (the )?(editor|generator)|invoice generator|use (the )?template)\b/i;
      const entry = page.locator('button, a[role=button], a');
      const count = Math.min(await entry.count(), 40);
      for (let i = 0; i < count; i++) {
        let t = '';
        try { t = ((await entry.nth(i).innerText({ timeout: 800 })) || '').trim(); } catch { continue; }
        if (!t || !ENTRY.test(t)) continue;
        try {
          await entry.nth(i).click({ timeout: 5000 });
          evidence.notes.push('clicked "' + t.slice(0, 40).replace(/\s+/g, ' ') + '" to reach the editor');
          await page.waitForTimeout(7000);
          filled = await fillEverywhere();
          break;
        } catch { /* keep looking */ }
      }
    }
    evidence.fillable_fields = filled.candidates;
    evidence.fields_filled = filled.filled;
    evidence.field_map = filled.map;

    let password = 0;
    for (const f of page.frames()) {
      try { password += await f.locator('input[type=password]').count(); } catch { }
    }
    evidence.login_form_present = password > 0;
    if (filled.filled === 0) {
      evidence.notes.push(password > 0
        ? 'a sign-in form is on the page and no editor was reachable: the editor is behind an account'
        : 'no editable invoice fields were reachable on this page');
    }
    await page.waitForTimeout(2500);

    if (filled.filled > 0) {
      const RANKED = [
        /download\s*(the\s*)?(pdf|invoice)?/i, /get\s*(the\s*)?pdf/i, /export/i,
        /generate/i, /create\s*(the\s*)?invoice/i, /make\s*(an?\s*)?invoice/i,
        /preview/i, /save/i, /continue/i,
      ];
      const buttons = page.locator('button, a[role=button], input[type=submit], a');
      const count = Math.min(await buttons.count(), 80);
      const found = [];
      for (let i = 0; i < count; i++) {
        let t = '';
        try { t = ((await buttons.nth(i).innerText({ timeout: 800 })) || '').trim(); } catch { continue; }
        if (!t || t.length > 40) continue;
        const rank = RANKED.findIndex((re) => re.test(t));
        if (rank >= 0) found.push({ rank, i, t });
      }
      found.sort((a, b) => a.rank - b.rank);
      for (const cand of found.slice(0, 3)) {
        try {
          const el = buttons.nth(cand.i);
          if (!(await el.isVisible()) || !(await el.isEnabled())) continue;
          await el.click({ timeout: 5000 });
          evidence.action_clicked = (evidence.action_clicked ? evidence.action_clicked + ' | ' : '')
            + cand.t.slice(0, 40).replace(/\s+/g, ' ');
          await page.waitForTimeout(7000);
          if (evidence.pdf_downloaded) break;
        } catch { /* a control that will not take a click is not a measurement */ }
      }
      await page.waitForTimeout(4000);
    }

    const host = registrable(evidence.final_url || URL_ARG);
    const base = CANARY.toLowerCase();
    const tokenAt = new RegExp(base + 'f(\\d+)', 'gi');
    const byField = new Map(filled.map.map((f) => [f.token.toLowerCase(), f]));
    const seen = new Map();
    const leaked = new Map();
    for (const r of requests.slice(beforeTyping)) {
      const haystack = (r.url + ' ' + (r.body || '')).toLowerCase();
      if (!haystack.includes(base)) continue;
      const domain = registrable(r.url);
      if (!seen.has(domain)) {
        seen.set(domain, {
          domain, method: r.method, url: r.url.slice(0, 300),
          where: r.url.toLowerCase().includes(base) ? 'url' : 'request body',
          first_party: sameSite(domain, host),
        });
      }
      for (const match of haystack.matchAll(tokenAt)) {
        const field = byField.get(match[0]);
        if (!field) continue;
        // Keyed by field AND destination. Keying by field alone recorded only
        // wherever a value went first, so a second recipient of the same field
        // silently disappeared -- and "which company got the customer's name"
        // is the only thing this study is really being asked.
        const key = field.token + '->' + domain;
        if (!leaked.has(key)) {
          leaked.set(key, {
            type: field.type, name: field.name, id: field.id,
            placeholder: field.placeholder, label: field.label,
            sent_to: domain, first_party: sameSite(domain, host),
          });
        }
      }
    }
    evidence.canary_destinations = [...seen.values()];
    evidence.leaked_fields = [...leaked.values()];
    evidence.canary_left_the_browser = filled.filled === 0 ? null : seen.size > 0;
    evidence.canary_left_to_third_party = filled.filled === 0
      ? null : [...seen.values()].some((d) => !d.first_party);

    const third = new Set(), ads = new Set();
    for (const r of requests) {
      const d = registrable(r.url);
      if (!d || sameSite(d, host)) continue;
      third.add(d);
      if (AD_TRACKER.some((a) => r.url.includes(a))) ads.add(d);
    }
    evidence.third_party_domains = [...third].sort();
    evidence.ad_tracker_domains = [...ads].sort();

    await page.screenshot({ path: path.join(OUT_DIR, 'screenshot.png') }).catch(() => { });
    fs.writeFileSync(path.join(OUT_DIR, 'requests.json'), JSON.stringify(
      requests.slice(beforeTyping).map((r) => ({ method: r.method, url: r.url, body_len: r.body ? r.body.length : 0 })), null, 2));
  } catch (error) {
    evidence.notes.push('measurement error: ' + String(error.message || error).slice(0, 300));
  } finally {
    if (browser) await browser.close().catch(() => { });
  }

  fs.writeFileSync(path.join(OUT_DIR, 'evidence.json'), JSON.stringify(evidence, null, 2));
  console.log(JSON.stringify({
    url: evidence.url, filled: evidence.fields_filled, egress: evidence.canary_left_the_browser,
    third_party: evidence.canary_left_to_third_party,
    to: evidence.canary_destinations.map((d) => d.domain),
    leaked: evidence.leaked_fields.map((f) => f.name || f.placeholder || f.label || f.type),
    tp: evidence.third_party_domains.length, notes: evidence.notes,
  }));
})();
