import type { APIRoute } from 'astro';
import { generators } from '@/content/generators';

/**
 * Routes that are their own .astro file rather than a `generators` entry.
 * Listing them by hand is a liability -- the progress draw schedule shipped
 * missing from the sitemap because this file only read `generators` -- so the
 * e2e suite asserts every canonical page appears here, and that check is what
 * makes the hand-maintained half safe.
 */
const standalonePaths = ['/progress-draw-schedule/', '/research/free-invoice-generator-audit-2026/'];
const staticPaths = ['/about/', '/privacy/', '/terms/', '/contact/'];

export const GET: APIRoute = () => {
  const urls = [
    ...Object.values(generators).map((page) => page.path),
    ...standalonePaths,
    ...staticPaths,
  ]
    .map((path) => `<url><loc>${new URL(path, 'https://invoiceworkshop.com').toString()}</loc></url>`)
    .join('');
  return new Response(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
