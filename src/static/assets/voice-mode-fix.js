(function(){
  const origFetch = window.fetch ? window.fetch.bind(window) : null;
  if (!origFetch) return;

  let speakingAudio = null;
  let currentUtterance = null;

  function stopSpeech(){
    try {
      if (speakingAudio) {
        speakingAudio.pause();
        speakingAudio.src = '';
        speakingAudio = null;
      }
    } catch {}
    try {
      if (window.speechSynthesis) {
        window.speechSynthesis.cancel();
      }
    } catch {}
    currentUtterance = null;
  }

  async function speakText(text){
    text = (text || '').trim();
    if (!text) return;
    stopSpeech();

    try {
      const resp = await origFetch('/api/tts', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({ text })
      });
      if (resp.ok) {
        const blob = await resp.blob();
        const url = URL.createObjectURL(blob);
        const audio = new Audio(url);
        speakingAudio = audio;
        audio.onended = () => {
          URL.revokeObjectURL(url);
          if (speakingAudio === audio) speakingAudio = null;
        };
        audio.onerror = () => {
          URL.revokeObjectURL(url);
          if (speakingAudio === audio) speakingAudio = null;
        };
        await audio.play();
        return;
      }
    } catch (e) {
      console.warn('Server TTS playback failed, falling back to browser speech:', e);
    }

    if (!window.speechSynthesis) return;
    const utterance = new SpeechSynthesisUtterance(text);
    utterance.rate = 1;
    utterance.pitch = 0.95;
    utterance.volume = 1;
    const voices = window.speechSynthesis.getVoices ? window.speechSynthesis.getVoices() : [];
    const preferred = voices.find(v => v.name.includes('Google') && v.lang.startsWith('en')) || voices.find(v => v.lang.startsWith('en-GB')) || voices.find(v => v.lang.startsWith('en'));
    if (preferred) utterance.voice = preferred;
    currentUtterance = utterance;
    window.speechSynthesis.speak(utterance);
  }

  window.__jarvisVoiceMode = {
    speakText,
    stopSpeech,
  };

  window.fetch = async function(input, init){
    const res = await origFetch(input, init);
    try {
      const url = typeof input === 'string' ? input : (input && input.url) || '';
      if (url.includes('/api/ollama/generate') && res.ok) {
        const clone = res.clone();
        const data = await clone.json().catch(() => null);
        const text = data && (data.response || data.text);
        if (text) {
          setTimeout(() => { speakText(text).catch(() => {}); }, 0);
        }
      }
    } catch (e) {}
    return res;
  };
})();
