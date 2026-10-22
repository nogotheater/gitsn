/* 홈 화면 앱(PWA)용 최소 서비스 워커(2026-10-22). 고객 자료는 저장하지 않는다 — 늘 서버에서 새로 받는다.
   인터넷이 끊겼을 때 화면 이동만 '연결을 확인해 주세요' 안내로 바꾼다. */
self.addEventListener('install', () => self.skipWaiting());
self.addEventListener('activate', event => event.waitUntil(self.clients.claim()));
self.addEventListener('fetch', event => {
  if (event.request.mode !== 'navigate') return;
  event.respondWith(fetch(event.request).catch(() => new Response(
    '<!doctype html><html lang="ko"><meta charset="utf-8"><meta name="viewport" content="width=device-width,initial-scale=1"><title>GITSN</title>' +
    '<body style="margin:0;display:grid;place-items:center;min-height:100vh;font-family:sans-serif;background:#F2F5F8;color:#383737">' +
    '<p style="text-align:center;line-height:1.6">인터넷 연결을 확인해 주세요.<br><small>연결되면 다시 열어 주세요.</small></p></body></html>',
    {headers: {'Content-Type': 'text/html; charset=utf-8'}, status: 503})));
});
