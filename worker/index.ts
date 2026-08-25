interface Env {
  ASSETS: { fetch(request: Request): Promise<Response> };
}

const canonicalHost = 'invoiceworkshop.com';

export default {
  async fetch(request: Request, env: Env): Promise<Response> {
    const url = new URL(request.url);

    if (url.protocol !== 'https:' || url.hostname === `www.${canonicalHost}`) {
      url.protocol = 'https:';
      url.hostname = canonicalHost;
      return Response.redirect(url.toString(), 301);
    }

    const response = await env.ASSETS.fetch(request);
    if (url.hostname === canonicalHost) return response;

    const headers = new Headers(response.headers);
    headers.set('X-Robots-Tag', 'noindex, nofollow, noarchive');
    return new Response(response.body, {
      status: response.status,
      statusText: response.statusText,
      headers,
    });
  },
};
