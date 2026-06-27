// Cloudflare Worker - Amazon UK Proxy (Service Worker format)
const ALLOWED_DOMAINS = ['www.amazon.co.uk', 'amazon.co.uk'];
const ALLOWED_PATHS = [
  '/gp/new-releases/', '/gp/bestsellers/', '/gp/most-wished-for/',
  '/gp/gifts/', '/gp/movers-and-shakers/', '/s?k=', '/dp/',
];

async function handleRequest(request) {
  const url = new URL(request.url);
  const targetUrl = url.searchParams.get('url');
  if (!targetUrl) {
    return new Response('Missing url parameter', { status: 400 });
  }
  
  let target;
  try { target = new URL(targetUrl); } catch {
    return new Response('Invalid URL', { status: 400 });
  }
  
  if (!ALLOWED_DOMAINS.some(d => target.hostname.endsWith(d))) {
    return new Response('Domain not allowed', { status: 403 });
  }
  if (!ALLOWED_PATHS.some(p => target.pathname.startsWith(p))) {
    return new Response('Path not allowed', { status: 403 });
  }
  
  const response = await fetch(targetUrl, {
    headers: {
      'User-Agent': 'Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36',
      'Accept-Language': 'en-GB,en;q=0.9',
      'Cookie': 'lc-main=en_GB; i18n-prefs=GBP',
    },
  });
  
  const h = new Headers(response.headers);
  h.set('Access-Control-Allow-Origin', '*');
  return new Response(response.body, { status: response.status, headers: h });
}

addEventListener('fetch', event => {
  event.respondWith(handleRequest(event.request));
});
