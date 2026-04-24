(function(){
  const origFetch = window.fetch ? window.fetch.bind(window) : null;
  if (!origFetch) return;
  window.fetch = async function(input, init){
    const res = await origFetch(input, init);
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url.includes('/api/openclaw/map') && res.ok) {
        const clone = res.clone();
        const data = await clone.json();
        if (data && data.services_live && data.services_live.OpenClaw && data.services_live.OpenClaw.status === 'online') {
          console.log('[jarvis-fix] openclaw map confirms backend online');
        }
      }
    } catch (e) {}
    return res;
  };
})();
