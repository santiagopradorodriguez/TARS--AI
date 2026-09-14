
// Desbloquear audio en movil al primer toque en la pantalla
let audioUnlocked = false;
function unlockMobileAudio() {
    if (!audioUnlocked) {
        const silentAudio = new Audio("data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA");
        silentAudio.play().then(() => {
            audioUnlocked = true;
        }).catch(() => {});
    }
}
document.addEventListener('touchstart', unlockMobileAudio, { passive: true });
document.addEventListener('click', unlockMobileAudio, { passive: true });

let isRecording = false;
let mediaRecorder = null;
let audioChunks = [];
let recordStartTime = 0;

const chatContainer = document.getElementById('chat-container');
const textInput = document.getElementById('text-input');
const sendBtn = document.getElementById('send-btn');
const micBtn = document.getElementById('mic-btn');
const micStatusLabel = document.getElementById('mic-status-label');

// Gestor de Audio Unificado (Pausa / Reanudar / Detener y anti-solapamiento)
let currentAudio = null;
let currentAudioBtn = null;
let currentAudioUrl = null;

const audioControlBar = document.getElementById('audio-control-bar');
const audioStatusText = document.getElementById('audio-status-text');
const audioPauseBtn = document.getElementById('audio-pause-btn');
const audioStopBtn = document.getElementById('audio-stop-btn');
const pauseIcon = document.getElementById('pause-icon');
const playIcon = document.getElementById('play-icon');

function stopCurrentAudio() {
    if (currentAudio) {
        currentAudio.pause();
        currentAudio.currentTime = 0;
        currentAudio = null;
    }
    if (currentAudioBtn) {
        currentAudioBtn.classList.remove('playing', 'paused');
        currentAudioBtn.querySelector('span').innerText = 'Escuchar respuesta';
        currentAudioBtn = null;
    }
    currentAudioUrl = null;
    if (audioControlBar) {
        audioControlBar.classList.add('hidden');
    }
}

function pauseCurrentAudio() {
    if (currentAudio && !currentAudio.paused) {
        currentAudio.pause();
        if (pauseIcon) pauseIcon.style.display = 'none';
        if (playIcon) playIcon.style.display = 'inline';
        if (audioStatusText) audioStatusText.innerText = 'Voz pausada';
        if (currentAudioBtn) {
            currentAudioBtn.classList.remove('playing');
            currentAudioBtn.classList.add('paused');
            currentAudioBtn.querySelector('span').innerText = 'Reanudar voz';
        }
    }
}

function resumeCurrentAudio() {
    if (currentAudio && currentAudio.paused) {
        currentAudio.play().then(() => {
            if (pauseIcon) pauseIcon.style.display = 'inline';
            if (playIcon) playIcon.style.display = 'none';
            if (audioStatusText) audioStatusText.innerText = 'Elena hablando...';
            if (currentAudioBtn) {
                currentAudioBtn.classList.remove('paused');
                currentAudioBtn.classList.add('playing');
                currentAudioBtn.querySelector('span').innerText = 'Pausar voz';
            }
        }).catch(() => {});
    }
}

function playAudioUrl(url, sourceBtn = null) {
    if (!url) return;

    // Si tocamos el boton del audio que ya esta sonando: toggle pausa/reanudar
    if (currentAudio && currentAudioUrl === url) {
        if (currentAudio.paused) {
            resumeCurrentAudio();
        } else {
            pauseCurrentAudio();
        }
        return;
    }

    // Detener cualquier audio que estuviera sonando previamente
    stopCurrentAudio();

    const audio = new Audio(url);
    currentAudio = audio;
    currentAudioUrl = url;
    currentAudioBtn = sourceBtn;

    audio.onended = () => {
        stopCurrentAudio();
    };

    audio.onerror = () => {
        stopCurrentAudio();
    };

    audio.play().then(() => {
        if (audioControlBar) {
            audioControlBar.classList.remove('hidden');
            if (pauseIcon) pauseIcon.style.display = 'inline';
            if (playIcon) playIcon.style.display = 'none';
            if (audioStatusText) audioStatusText.innerText = 'Elena hablando...';
        }
        if (sourceBtn) {
            sourceBtn.classList.remove('paused');
            sourceBtn.classList.add('playing');
            sourceBtn.querySelector('span').innerText = 'Pausar voz';
        }
    }).catch(err => {
        console.log("Autoplay requiere tocar la pantalla al menos una vez:", err);
        stopCurrentAudio();
    });
}

if (audioPauseBtn) {
    audioPauseBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentAudio) {
            if (currentAudio.paused) {
                resumeCurrentAudio();
            } else {
                pauseCurrentAudio();
            }
        }
    });
}

if (audioStopBtn) {
    audioStopBtn.addEventListener('click', (e) => {
        e.preventDefault();
        stopCurrentAudio();
    });
}

function appendMessage(sender, text, media = null, audioUrl = null, autoPlay = true) {
    const msgDiv = document.createElement('div');
    msgDiv.className = `message ${sender}`;

    const contentDiv = document.createElement('div');
    contentDiv.className = 'message-content';

    const p = document.createElement('p');
    p.innerText = text;
    contentDiv.appendChild(p);

    if (media && media.length > 0) {
        const mediaContainer = document.createElement('div');
        mediaContainer.className = 'media-container';

        media.forEach(item => {
            if (item.type === 'image') {
                const img = document.createElement('img');
                img.src = item.url;
                img.className = 'media-image';
                img.onclick = () => window.open(item.url, '_blank');
                mediaContainer.appendChild(img);
            } else if (item.type === 'file') {
                const a = document.createElement('a');
                a.href = item.url;
                a.className = 'file-card';
                a.download = item.name || 'archivo';
                a.innerHTML = `
                    <div class="file-info">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                            <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/>
                        </svg>
                        <span class="file-name">${item.name || 'Archivo adjunto'}</span>
                    </div>
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                        <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                    </svg>
                `;
                mediaContainer.appendChild(a);
            }
        });
        contentDiv.appendChild(mediaContainer);
    }

    if (audioUrl) {
        const audioBtn = document.createElement('button');
        audioBtn.className = 'audio-player-btn';
        audioBtn.innerHTML = `
            <svg viewBox="0 0 24 24" width="14" height="14" fill="currentColor">
                <path d="M3 9v6h4l5 5V4L7 9H3zm13.5 3c0-1.77-1.02-3.29-2.5-4.03v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06c2.89.86 5 3.54 5 6.71s-2.11 5.85-5 6.71v2.06c4.01-.91 7-4.49 7-8.77s-2.99-7.86-7-8.77z"/>
            </svg>
            <span>Escuchar respuesta</span>
        `;
        audioBtn.onclick = () => {
            playAudioUrl(audioUrl, audioBtn);
        };
        contentDiv.appendChild(audioBtn);

        // Auto-reproducir por voz si corresponde
        if (sender === 'assistant' && autoPlay) {
            playAudioUrl(audioUrl, audioBtn);
        }
    }

    msgDiv.appendChild(contentDiv);
    chatContainer.appendChild(msgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

async function sendTextMessage(text) {
    if (!text.trim()) return;
    appendMessage('user', text);
    textInput.value = '';

    try {
        const resp = await fetch('/api/chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ text: text })
        });
        const data = await resp.json();
        if (data.sent_to_ide) {
            // El mensaje ya fue inyectado en Antigravity IDE; esperamos la respuesta en vivo via /api/sync
            micStatusLabel.innerText = 'Antigravity procesando en PC...';
        } else if (data.reply) {
            // Respuesta de comando local (Spotify, screenshot, etc.)
            appendMessage('assistant', data.reply, data.media, data.audio_url);
        }
    } catch (err) {
        appendMessage('assistant', 'Error de conexion con el servidor local.');
    }
}

async function sendAudioBlob(blob) {
    appendMessage('user', '[Mensaje de voz enviado]');

    const formData = new FormData();
    formData.append('audio', blob, 'voice.webm');

    try {
        micStatusLabel.innerText = 'Transcribiendo...';
        const resp = await fetch('/api/audio', {
            method: 'POST',
            body: formData
        });
        const data = await resp.json();
        
        if (data.user_text) {
            // Reemplazar mensaje de usuario con el texto transcripto
            const msgs = document.querySelectorAll('.message.user');
            if (msgs.length > 0) {
                msgs[msgs.length - 1].querySelector('p').innerText = data.user_text;
            }
        }

        if (data.sent_to_ide) {
            // Inyectado a Antigravity IDE
            micStatusLabel.innerText = 'Antigravity procesando en PC...';
        } else if (data.reply) {
            appendMessage('assistant', data.reply, data.media, data.audio_url);
            micStatusLabel.innerText = 'Toca para hablar';
        }
    } catch (err) {
        appendMessage('assistant', 'Error al procesar el audio en la PC.');
        micStatusLabel.innerText = 'Toca para hablar';
    }
}

async function startRecording() {
    if (isRecording) return;
    try {
        const stream = await navigator.mediaDevices.getUserMedia({ audio: true });
        mediaRecorder = new MediaRecorder(stream);
        audioChunks = [];

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = () => {
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            stream.getTracks().forEach(track => track.stop());
            if (audioChunks.length > 0) {
                sendAudioBlob(audioBlob);
            }
        };

        mediaRecorder.start();
        isRecording = true;
        recordStartTime = Date.now();
        micBtn.classList.add('recording');
        micStatusLabel.innerText = 'Escuchando... Toca para enviar';
    } catch (err) {
        alert('No se pudo acceder al microfono. Asegurate de dar permisos HTTPS en el navegador.');
    }
}

function stopRecording() {
    if (!isRecording || !mediaRecorder) return;
    isRecording = false;
    micBtn.classList.remove('recording');
    micStatusLabel.innerText = 'Enviando...';
    mediaRecorder.stop();
}

// Toggle grabacion al hacer clic
micBtn.addEventListener('click', (e) => {
    e.preventDefault();
    if (!isRecording) {
        startRecording();
    } else {
        stopRecording();
    }
});

// Envio de texto
sendBtn.addEventListener('click', () => {
    sendTextMessage(textInput.value);
});

textInput.addEventListener('keydown', (e) => {
    if (e.key === 'Enter') {
        sendTextMessage(textInput.value);
    }
});

// Sincronizacion en tiempo real con la sesion activa de Antigravity
let currentSyncIndex = 0;

async function syncWithAntigravity() {
    try {
        const resp = await fetch(`/api/sync?last_index=${currentSyncIndex}`);
        const data = await resp.json();
        if (data.has_new && data.step_index > currentSyncIndex) {
            currentSyncIndex = data.step_index;
            appendMessage('assistant', data.content, data.media, data.audio_url, true);
            micStatusLabel.innerText = 'Toca para hablar';
        } else if (data.step_index && currentSyncIndex === 0) {
            // Inicializar al ultimo indice para no duplicar historico viejo
            currentSyncIndex = data.step_index;
        }
    } catch (e) {
        // Silencioso ante breves desconexiones
    }
}

setInterval(syncWithAntigravity, 1500);
syncWithAntigravity();
