import type { APIRoute } from 'astro';
import { generators } from '@/content/generators';

const staticPaths = ['/about/', '/privacy/', '/terms/', '/contact/'];

export const GET: APIRoute = () => {
  const urls = [...Object.values(generators).map((page) => page.path), ...staticPaths]
    .map((path) => `<url><loc>${new URL(path, 'https://invoiceworkshop.com').toString()}</loc></url>`)
    .join('');
  return new Response(`<?xml version="1.0" encoding="UTF-8"?><urlset xmlns="http://www.sitemaps.org/schemas/sitemap/0.9">${urls}</urlset>`, {
    headers: { 'Content-Type': 'application/xml; charset=utf-8' },
  });
};
