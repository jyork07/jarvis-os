(function() {
    let audioContext = null;
    let analyser = null;
    let microphone = null;
    let mediaRecorder = null;
    let audioChunks = [];
    let isListening = false;
    let isRecording = false;
    let silenceTimeout = null;
    let speechStartTime = null;

    // VAD thresholds - adjusted to filter out TV/background noise
    const SILENCE_THRESHOLD = 0.015;  // Volume threshold for silence (lowered)
    const SPEECH_THRESHOLD = 0.08;   // Volume threshold to detect speech start (raised)
    const MIN_SPEECH_DURATION = 500; // Minimum speech duration (ms) (increased)
    const SILENCE_DURATION = 600;    // Silence duration before stopping (ms)

    function beep(frequency = 880, duration = 80, volume = 0.03) {
        try {
            const AudioCtx = window.AudioContext || window.webkitAudioContext;
            if (!AudioCtx) return;
            const ctx = new AudioCtx();
            const osc = ctx.createOscillator();
            const gain = ctx.createGain();
            osc.type = 'sine';
            osc.frequency.value = frequency;
            gain.gain.value = volume;
            osc.connect(gain);
            gain.connect(ctx.destination);
            osc.start();
            setTimeout(() => {
                try { osc.stop(); } catch {}
                try { ctx.close(); } catch {}
            }, duration);
        } catch {}
    }

    function setListeningVisual(active) {
        const bubble = document.getElementById('mic-status-bubble');
        if (bubble) bubble.style.display = active ? 'block' : 'none';
        
        // Dispatch event for dashboard
        try {
            document.dispatchEvent(new CustomEvent('jarvis-listening', { detail: { active } }));
        } catch {}
    }

    function setThinkingVisual(active) {
        try {
            document.dispatchEvent(new CustomEvent('jarvis-thinking', { detail: { active } }));
        } catch {}
    }

    function updateMicButton(active) {
        const btn = document.getElementById('mic-button');
        if (btn) {
            if (active) {
                btn.classList.add('active');
            } else {
                btn.classList.remove('active');
            }
        }
    }

    function getVolumeLevel(analyser) {
        const dataArray = new Uint8Array(analyser.frequencyBinCount);
        analyser.getByteFrequencyData(dataArray);
        let sum = 0;
        for (let i = 0; i < dataArray.length; i++) {
            sum += dataArray[i];
        }
        return sum / dataArray.length / 255;  // Normalize to 0-1
    }

    async function startListening() {
        if (isListening) return;

        try {
            const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
            
            audioContext = new (window.AudioContext || window.webkitAudioContext)();
            analyser = audioContext.createAnalyser();
            analyser.fftSize = 256;
            microphone = audioContext.createMediaStreamSource(stream);
            microphone.connect(analyser);

            // Set up MediaRecorder for actual recording
            const preferredMimeTypes = [
                'audio/webm;codecs=opus',
                'audio/webm',
                'audio/ogg;codecs=opus',
                'audio/ogg'
            ];
            const mimeType = preferredMimeTypes.find(type => window.MediaRecorder && MediaRecorder.isTypeSupported && MediaRecorder.isTypeSupported(type)) || '';
            mediaRecorder = mimeType ? new MediaRecorder(stream, { mimeType }) : new MediaRecorder(stream);

            mediaRecorder.ondataavailable = (event) => {
                if (event.data && event.data.size > 0) {
                    audioChunks.push(event.data);
                }
            };

            mediaRecorder.onstop = async () => {
                const actualMimeType = mediaRecorder.mimeType || mimeType || 'audio/webm';
                const extension = actualMimeType.includes('ogg') ? 'ogg' : 'webm';
                const audioBlob = new Blob(audioChunks, { type: actualMimeType });
                setListeningVisual(false);
                setThinkingVisual(true);
                await sendToJarvis(audioBlob, `recording.${extension}`);
                setThinkingVisual(false);
                audioChunks = [];
            };

            isListening = true;
            setListeningVisual(true);
            updateMicButton(true);
            beep(880, 50, 0.02);

            // Start VAD loop
            detectSpeech();

        } catch (err) {
            console.error('Mic access denied or error:', err);
            alert('Microphone access denied. Please ensure you are using HTTPS and have granted permissions.');
        }
    }

    function detectSpeech() {
        if (!isListening || !analyser) return;

        const volume = getVolumeLevel(analyser);

        if (!isRecording && volume > SPEECH_THRESHOLD) {
            // Speech detected - start recording
            speechStartTime = Date.now();
            audioChunks = [];
            mediaRecorder.start(100);
            isRecording = true;
            beep(920, 70, 0.035);
            console.log('Speech detected, started recording');
        } else if (isRecording) {
            if (volume < SILENCE_THRESHOLD) {
                // Silence detected
                if (!silenceTimeout) {
                    silenceTimeout = setTimeout(() => {
                        const speechDuration = Date.now() - speechStartTime;
                        if (speechDuration > MIN_SPEECH_DURATION) {
                            // Valid speech ended - stop recording
                            stopRecording();
                        } else {
                            // Too short - discard and reset
                            mediaRecorder.stop();
                            audioChunks = [];
                            isRecording = false;
                            console.log('Speech too short, discarded');
                        }
                        silenceTimeout = null;
                    }, SILENCE_DURATION);
                }
            } else {
                // Still speaking - cancel silence timeout
                if (silenceTimeout) {
                    clearTimeout(silenceTimeout);
                    silenceTimeout = null;
                }
            }
        }

        requestAnimationFrame(detectSpeech);
    }

    function stopRecording() {
        if (mediaRecorder && isRecording) {
            beep(620, 90, 0.03);
            mediaRecorder.stop();
            isRecording = false;
            setListeningVisual(false);
            console.log('Recording stopped');
        }
    }

    function stopListening() {
        if (!isListening) return;
        
        isListening = false;
        setListeningVisual(false);
        updateMicButton(false);
        
        if (mediaRecorder && isRecording) {
            stopRecording();
        }
        
        if (microphone) {
            microphone.disconnect();
        }
        
        if (audioContext) {
            audioContext.close();
        }
        
        if (silenceTimeout) {
            clearTimeout(silenceTimeout);
            silenceTimeout = null;
        }
        
        beep(620, 50, 0.02);
        console.log('Listening stopped');
    }

    async function sendToJarvis(blob, filename = 'recording.webm') {
        // Validate blob size before sending
        if (!blob || blob.size < 500) {
            console.error('Audio blob too small:', blob ? blob.size : 0, 'bytes');
            return;
        }

        console.log('Sending audio blob:', blob.size, 'bytes, type:', blob.type);
        const formData = new FormData();
        formData.append('audio', blob, filename);

        try {
            // Step 1: Transcribe
            const transcribeResp = await fetch('/api/voice/transcribe', {
                method: 'POST',
                body: formData
            });
            const transcribeData = await transcribeResp.json();
            
            if (!transcribeData.ok || !transcribeData.text) {
                console.error('Transcription failed:', transcribeData);
                return;
            }

            console.log('Transcribed:', transcribeData.text);

            // Step 2: Get AI response
            const generateResp = await fetch('/api/ollama/generate', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ prompt: transcribeData.text })
            });
            const generateData = await generateResp.json();
            
            const responseText = generateData.response || generateData.text || '';
            if (!responseText) {
                console.error('No response from AI');
                return;
            }

            console.log('AI response:', responseText);

            // Step 3: Display in chat (React app will handle TTS)
            const input = document.querySelector('input[type="text"], textarea, .chat-input');
            if (input) {
                input.value = transcribeData.text;
                input.dispatchEvent(new Event('input', { bubbles: true }));
                setTimeout(() => {
                    const sendBtn = document.querySelector('button[type="submit"], button:has(svg)');
                    if (sendBtn) {
                        sendBtn.click();
                    } else {
                        input.dispatchEvent(new KeyboardEvent('keydown', { key: 'Enter', bubbles: true }));
                    }
                }, 100);
            }

        } catch (err) {
            console.error('Voice chat failed:', err);
        }
    }

    async function playTTS(text) {
        try {
            const ttsResp = await fetch('/api/tts', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ text: text })
            });

            if (!ttsResp.ok) {
                console.error('TTS failed:', ttsResp.status);
                return;
            }

            const audioBlob = await ttsResp.blob();
            const audioUrl = URL.createObjectURL(audioBlob);
            const audio = new Audio(audioUrl);
            
            audio.onended = () => {
                URL.revokeObjectURL(audioUrl);
            };
            
            await audio.play();
            console.log('Playing TTS response');

        } catch (err) {
            console.error('TTS playback failed:', err);
        }
    }

    // Space bar hold to listen
    document.addEventListener('DOMContentLoaded', () => {
        // Space bar hold to activate listening
        document.addEventListener('keydown', (e) => {
            if (e.code === 'Space' && !e.repeat && !e.target.closest('input, textarea')) {
                e.preventDefault();
                startListening();
            }
        });

        document.addEventListener('keyup', (e) => {
            if (e.code === 'Space' && !e.target.closest('input, textarea')) {
                e.preventDefault();
                stopListening();
            }
        });

        // Click mic button to toggle listening
        const micBtn = document.getElementById('mic-button');
        if (micBtn) {
            micBtn.addEventListener('click', (e) => {
                e.preventDefault();
                if (isListening) {
                    stopListening();
                } else {
                    startListening();
                }
            });
        }
    });
})();
