(async () => {
  const request = __BRIDGE_REQUEST__;
  const respond = payload => window.__TAURI_INTERNALS__.invoke('bridge_response', {
    id: request.request_id, nonce: request.nonce, payload
  }).catch(() => {});
  if (location.origin !== 'https://www.douyin.com') {
    return respond({error: '请等待抖音首页加载完成', code: 'PAGE_LOAD_FAILED'});
  }
  try {
    if (document.readyState !== 'complete') {
      await Promise.race([new Promise(resolve => addEventListener('load', resolve, {once:true})), new Promise(resolve => setTimeout(resolve, 5000))]);
    }
    const url = new URL(request.path, location.origin);
    if (url.origin !== location.origin || !url.pathname.startsWith('/aweme/v1/web/')) throw Error('Invalid endpoint');
    for (const [key, value] of Object.entries(request.params || {})) {
      if (value != null && value !== '' && !['a_bogus', 'X-Bogus', 'msToken', 'verifyFp', 'fp'].includes(key)) url.searchParams.set(key, String(value));
    }
    url.searchParams.set('browser_name', 'Edge');
    url.searchParams.set('browser_version', navigator.userAgent.match(/(?:Edg|Chrome)\/([\d.]+)/)?.[1] || '120.0.0.0');
    url.searchParams.set('screen_width', String(screen.width));
    url.searchParams.set('screen_height', String(screen.height));
    url.searchParams.set('browser_language', navigator.language);
    // Use the page's current fetch implementation, allowing its SDK to sign the request.
    const response = await window.fetch(url.href, {credentials:'include', signal: AbortSignal.timeout(35000)});
    const text = await response.text();
    let body = null;
    try { body = JSON.parse(text); } catch {}
    await respond({http_status:response.status, body, text:body ? '' : text.slice(0, 300)});
  } catch {
    await respond({error:'页面请求失败或超时，请检查网络并在抖音窗口完成验证', code:'PAGE_ERROR'});
  }
})();
