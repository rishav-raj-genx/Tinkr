        // ── DOM Elements ──
        const UI = {
            setupModal: document.getElementById('setupModal'),
            startBtn: document.getElementById('startSessionBtn'),
            userIdInput: document.getElementById('userId'),
            callBtn: document.getElementById('callBtn'),
            statusText: document.getElementById('statusText'),
            transcriptStream: document.getElementById('transcriptStream'),
            orbContainer: document.getElementById('orbContainer'),
            sidebar: document.getElementById('sidebar'),
            historyBtn: document.getElementById('historyBtn'),
            closeSidebar: document.getElementById('closeSidebar'),
            historyContent: document.getElementById('historyContent'),
            wellnessModal: document.getElementById('wellnessModal'),
            wellnessIcon: document.getElementById('wellnessIcon'),
            wellnessTitle: document.getElementById('wellnessTitle'),
            wellnessDesc: document.getElementById('wellnessDesc')
        };

        // ── State ──
        let isCallActive = false;
        let visualizerId = null;
        let ttsQueue = [];
        let isPlayingTts = false;
        
        const SpeechRecognition = window.SpeechRecognition || window.webkitSpeechRecognition;
        let recognition = null;
        if (SpeechRecognition) {
            recognition = new SpeechRecognition();
            recognition.continuous = false;
            recognition.interimResults = false;
        }
        let audioChunks = [];
        let mediaStream = null;
        let currentUserId = '';
        let pendingBiomarkerData = null;
        let micAnalyser = null;

        // ── Navigation ──
        UI.historyBtn.addEventListener('click', () => {
            UI.sidebar.classList.add('open');
            if (currentUserId) loadHistory();
        });

        UI.closeSidebar.addEventListener('click', () => {
            UI.sidebar.classList.remove('open');
        });

        // ── Session Start ──
        UI.startBtn.addEventListener('click', async () => {
            currentUserId = UI.userIdInput.value.trim();
            if (!currentUserId) return alert("Please enter your name or ID.");

            UI.setupModal.classList.add('hidden');
            updateStatus('Ready to listen');
            setStreamText("Tap the microphone to start.", "system-text");
        });

        // ── Voice Interaction ──
        UI.callBtn.addEventListener('click', async () => {
            isCallActive = !isCallActive;

            if (isCallActive) {
                UI.callBtn.classList.add('active');
                UI.callBtn.innerHTML = '<span class="material-icons-round">stop</span>';
                updateStatus('Listening...');
                setStreamText("Listening...", "user-text");

                try {
                    mediaStream = await navigator.mediaDevices.getUserMedia({ audio: true });
                    
                    const audioContext = new (window.AudioContext || window.webkitAudioContext)();
                    micAnalyser = audioContext.createAnalyser();
                    micAnalyser.fftSize = 256;
                    const source = audioContext.createMediaStreamSource(mediaStream);
                    source.connect(micAnalyser);
                    startVisualizer();
                    
                    if (recognition) {
                        recognition.onresult = (event) => {
                            const transcript = event.results[0][0].transcript;
                            isCallActive = false;
                            resetCallBtnUI();
                            if (mediaStream) {
                                mediaStream.getTracks().forEach(t => t.stop());
                            }
                            processText(transcript);
                        };
                        recognition.onerror = (event) => {
                            console.error("Speech Recognition Error:", event.error);
                            isCallActive = false;
                            resetCallBtnUI();
                            setStreamText("Microphone access denied or error.", "system-text");
                        };
                        recognition.onend = () => {
                            if (isCallActive) {
                                isCallActive = false;
                                resetCallBtnUI();
                                if (mediaStream) {
                                    mediaStream.getTracks().forEach(t => t.stop());
                                }
                            }
                        };
                        recognition.start();
                    } else {
                        alert("Speech recognition is not supported in this browser.");
                        isCallActive = false;
                        resetCallBtnUI();
                    }

                } catch (err) {
                    console.error("Mic Error:", err);
                    isCallActive = false;
                    resetCallBtnUI();
                    setStreamText("Microphone access denied.", "system-text");
                }
            } else {
                resetCallBtnUI();
                if (recognition) {
                    recognition.stop();
                }
                updateStatus('Processing...');
                if (mediaStream) {
                    mediaStream.getTracks().forEach(t => t.stop());
                }
            }
        });

        function resetCallBtnUI() {
            UI.callBtn.classList.remove('active');
            UI.callBtn.innerHTML = '<span class="material-icons-round">mic</span>';
            UI.orbContainer.classList.remove('speaking-mode');
            if (visualizerId) cancelAnimationFrame(visualizerId);
            UI.callBtn.style.setProperty('--mic-scale', '1');
            UI.orbContainer.style.setProperty('--ai-scale', '0.5');
        }

        async function processText(text) {
            setStreamText(`"${text}"`, "user-text");
            setSpeakingState(true);
            updateStatus('Thinking...');
            
            try {
                const chatRes = await fetch('http://127.0.0.1:5000/api/chat_stream', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({
                        text: text,
                        user_id: currentUserId,
                        emotion_context: '' // Deprecated for ultra-low latency
                    })
                });
                
                const reader = chatRes.body.getReader();
                const decoder = new TextDecoder('utf-8');
                let sentenceBuffer = "";
                let fullResponse = "";
                
                setStreamText("", "ai-text");
                
                while (true) {
                    const { done, value } = await reader.read();
                    if (done) break;
                    
                    const chunkStr = decoder.decode(value, {stream: true});
                    const lines = chunkStr.split('\n');
                    
                    for (const line of lines) {
                        if (line.startsWith('data: ')) {
                            const dataStr = line.replace('data: ', '').trim();
                            if (dataStr) {
                                try {
                                    const dataObj = JSON.parse(dataStr);
                                    if (dataObj.text) {
                                        sentenceBuffer += dataObj.text;
                                        fullResponse += dataObj.text;
                                        
                                        // Update UI incrementally
                                        setStreamText(fullResponse, "ai-text");
                                        
                                        // Check for sentence boundary for TTS chunking
                                        if (/[.!?]\\s*$/.test(sentenceBuffer)) {
                                            queueTTS(sentenceBuffer.trim());
                                            sentenceBuffer = "";
                                        }
                                    } else if (dataObj.error) {
                                        setStreamText("Error: " + dataObj.error, "system-text");
                                    }
                                } catch(e) {
                                    console.error("JSON parse error on stream:", e, line);
                                }
                            }
                        }
                    }
                }
                
                // Flush remaining buffer
                if (sentenceBuffer.trim()) {
                    queueTTS(sentenceBuffer.trim());
                }
                
                updateStatus('Ready');
                setSpeakingState(false);
                
            } catch (err) {
                console.error("Pipeline Error:", err);
                setStreamText("Network error during processing.", "system-text");
                updateStatus('Ready');
                setSpeakingState(false);
            }
        }
        
        // ── TTS Queue System ──
        function queueTTS(text) {
            ttsQueue.push(text);
            processTtsQueue();
        }
        
        function processTtsQueue() {
            if (isPlayingTts || ttsQueue.length === 0) return;
            isPlayingTts = true;
            const text = ttsQueue.shift();
            speakText(text, () => {
                isPlayingTts = false;
                processTtsQueue();
            });
        }
        
        function speakText(text, onEndCallback) {
            } catch (err) {
                console.error("Pipeline Error:", err);
                setStreamText("Network error during processing.", "system-text");
                updateStatus('Ready');
            }
        }
        
        // ── TTS (Browser Native) ──
        function speakText(text) {
            if ('speechSynthesis' in window) {
                const utterance = new SpeechSynthesisUtterance(text);
                const voices = window.speechSynthesis.getVoices();
                const goodVoice = voices.find(v => v.name.includes("Google") || v.name.includes("Samantha") || v.name.includes("Siri"));
                if (goodVoice) utterance.voice = goodVoice;
                
                utterance.rate = 1.05; 
                
                utterance.onstart = () => {
                    UI.orbContainer.classList.add('speaking-mode');
                    startAiVisualizer();
                };
                utterance.onend = () => {
                    if (ttsQueue.length === 0) {
                        UI.orbContainer.classList.remove('speaking-mode');
                        UI.orbContainer.style.setProperty('--ai-scale', '0.5');
                        if(visualizerId) cancelAnimationFrame(visualizerId);
                    }
                    if (onEndCallback) onEndCallback();
                };
                utterance.onerror = () => {
                    if (onEndCallback) onEndCallback();
                };
                
                window.speechSynthesis.speak(utterance);
            } else {
                if (onEndCallback) onEndCallback();
            }
        }

        // ── Visualizer ──
        function startVisualizer() {
            const micData = new Uint8Array(micAnalyser.frequencyBinCount);
            function render() {
                if (!isCallActive) return;
                micAnalyser.getByteFrequencyData(micData);
                const micVol = micData.reduce((a, b) => a + b, 0) / micData.length;
                
                const micScale = 1.1 + (micVol / 255) * 0.3;
                UI.callBtn.style.setProperty('--mic-scale', micScale);
                visualizerId = requestAnimationFrame(render);
            }
            render();
        }

        function startAiVisualizer() {
            let t = 0;
            function render() {
                t += 0.1;
                const scale = 1.2 + Math.sin(t) * 0.2;
                UI.orbContainer.style.setProperty('--ai-scale', scale);
                if (UI.orbContainer.classList.contains('speaking-mode')) {
                    visualizerId = requestAnimationFrame(render);
                }
            }
            render();
        }

        // ── Wellness Modal Logic ──
        function triggerWellnessPrompt(bioData) {
            const icons = { stressed: 'warning', anxious: 'help_outline', fatigued: 'battery_alert', calm: 'self_improvement', unknown: 'question_mark' };
            UI.wellnessIcon.innerText = icons[bioData.predicted_state] || 'psychology';
            UI.wellnessTitle.innerText = `${bioData.predicted_state.charAt(0).toUpperCase() + bioData.predicted_state.slice(1)} Detected`;
            UI.wellnessDesc.innerText = `Voice analysis suggests you might be feeling ${bioData.predicted_state}. Is this accurate?`;
            UI.wellnessModal.classList.add('show');
        }

        async function confirmMentalState(confirmed) {
            UI.wellnessModal.classList.remove('show');
            if (!pendingBiomarkerData || !currentUserId) return;

            const payload = {
                user_id: currentUserId,
                predicted_state: pendingBiomarkerData.predicted_state,
                user_confirmed: confirmed,
                mean_zcr: pendingBiomarkerData.mean_zcr,
                rms_variance: pendingBiomarkerData.rms_variance,
                voice_energy_level: pendingBiomarkerData.voice_energy_level,
                suggestions: pendingBiomarkerData.suggestions || [],
            };

            try {
                await fetch('http://127.0.0.1:5000/api/save_mental_state', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify(payload)
                });
            } catch (err) {
                console.error("Save Error:", err);
            }
            pendingBiomarkerData = null;
        }
        window.confirmMentalState = confirmMentalState;

        // ── History Logic ──
        async function loadHistory() {
            UI.historyContent.innerHTML = '<p style="color: var(--text-dim); text-align: center;">Loading...</p>';
            try {
                const res = await fetch('http://127.0.0.1:5000/api/get_mental_state_history', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: JSON.stringify({ user_id: currentUserId, limit: 10 })
                });
                const data = await res.json();
                
                if (!data.success || data.history.length === 0) {
                    UI.historyContent.innerHTML = '<p style="color: var(--text-dim); text-align: center;">No logs available.</p>';
                    return;
                }

                UI.historyContent.innerHTML = data.history.map(entry => `
                    <div class="history-item">
                        <div class="history-item-header">
                            <span class="history-state">${entry.predicted_state}</span>
                            <span class="history-time">${new Date(entry.timestamp).toLocaleDateString()}</span>
                        </div>
                        <div class="history-details">
                            <div style="display:flex; align-items:center; gap:0.25rem; margin-bottom: 0.5rem;">
                                <span class="material-icons-round" style="font-size:1rem; color: ${entry.user_confirmed ? 'var(--success)' : 'var(--text-dim)'}">
                                    ${entry.user_confirmed ? 'check_circle' : 'radio_button_unchecked'}
                                </span>
                                ${entry.user_confirmed ? 'Confirmed by you' : 'Unconfirmed'}
                            </div>
                            Energy: ${entry.voice_energy_level}
                        </div>
                    </div>
                `).join('');
            } catch (err) {
                UI.historyContent.innerHTML = '<p style="color: var(--danger); text-align: center;">Error loading history.</p>';
            }
        }

        // ── Helpers ──
        function updateStatus(text) {
            UI.statusText.innerText = text;
        }

        function setSpeakingState(isSpeaking) {
            if (isSpeaking) {
                updateStatus('Tinkr is speaking...');
            } else if (!isCallActive) {
                updateStatus('Ready');
            }
        }

        function setStreamText(text, className) {
            UI.transcriptStream.innerHTML = `<div class="${className}" style="animation: fade-in 0.3s ease forwards;">${text}</div>`;
        }
