/**
 * The registrable domain of a URL.
 *
 * Enough of the public suffix list to stop "tools.rounded.com.au" being read as
 * the domain "com.au". Getting this wrong turned a tool posting to its own
 * server into a tool posting to a stranger, which is the single worst mistake
 * this study could publish, so it lives in its own file with its own tests.
 */
const MULTI_PART = new Set([
  'co.uk', 'org.uk', 'ac.uk', 'gov.uk', 'me.uk', 'net.uk', 'sch.uk',
  'com.au', 'net.au', 'org.au', 'edu.au', 'gov.au', 'id.au',
  'co.nz', 'net.nz', 'org.nz', 'co.za', 'org.za', 'co.in', 'net.in', 'org.in',
  'com.br', 'com.mx', 'com.ar', 'com.sg', 'com.my', 'com.hk', 'com.tw',
  'co.jp', 'ne.jp', 'or.jp', 'co.kr', 'com.tr', 'com.pl', 'com.ua', 'com.cn',
  'com.ph', 'com.vn', 'co.il', 'co.id', 'com.pk', 'com.ng', 'com.eg',
]);

const registrable = (u) => {
  try {
    const host = new URL(u).hostname.replace(/^www\./, '').toLowerCase();
    const parts = host.split('.');
    if (parts.length <= 2) return host;
    const lastTwo = parts.slice(-2).join('.');
    return MULTI_PART.has(lastTwo) ? parts.slice(-3).join('.') : lastTwo;
  } catch { return ''; }
};

/** Whether two registrable domains belong to the same operator. */
const sameSite = (a, b) => Boolean(a && b && (a === b || a.endsWith('.' + b) || b.endsWith('.' + a)));

module.exports = { registrable, sameSite, MULTI_PART };
