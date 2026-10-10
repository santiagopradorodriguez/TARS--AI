
function updateProcessingBubble(info) {
    let bubble = document.getElementById('processing-bubble');
    if (!bubble) {
        bubble = document.createElement('div');
        bubble.id = 'processing-bubble';
        bubble.className = 'message assistant processing-card';
        chatContainer.appendChild(bubble);
    }

    const thoughtText = info.thought ? escapeHtml(info.thought) : 'Pensando los próximos pasos...';
    let toolHtml = '';
    if (info.tool_action || info.tool_name) {
        const actionText = escapeHtml(info.tool_action || info.tool_name);
        const detailHtml = info.tool_detail ? `<div class="proc-detail">${escapeHtml(info.tool_detail)}</div>` : '';
        toolHtml = `
            <div class="processing-tool-box">
                <span class="proc-badge">⚡ ${escapeHtml(info.tool_name || 'Acción')}</span>
                <span>${actionText}</span>
                ${detailHtml}
            </div>
        `;
    }

    bubble.innerHTML = `
        <div class="processing-card-header">
            <span class="processing-pulse"></span>
            <span class="processing-title">Antigravity pensando y ejecutando...</span>
        </div>
        <div class="processing-thought-box">
            💭 ${thoughtText}
        </div>
        ${toolHtml}
    `;

    chatContainer.scrollTop = chatContainer.scrollHeight;
}

function removeProcessingBubble() {
    const bubble = document.getElementById('processing-bubble');
    if (bubble) {
        bubble.remove();
    }
}

// Helpers de formato y Markdown para TARS Movil
function escapeHtml(str) {
    return str
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

window.copyCode = function(btn) {
    const code = btn.closest('.code-block-wrapper').querySelector('code').innerText;
    navigator.clipboard.writeText(code).then(() => {
        const oldText = btn.innerText;
        btn.innerText = 'Copiado!';
        if (navigator.vibrate) navigator.vibrate(30);
        setTimeout(() => { btn.innerText = oldText; }, 2000);
    });
};

function renderMarkdown(text) {
    if (!text) return '';

    // 1. Extraer bloques de codigo multilinea
    const codeBlocks = [];
    const codeRegex = new RegExp('```([a-zA-Z0-9_-]*)[\\r\\n]+([\\s\\S]*?)```', 'g');
    let processed = text.replace(codeRegex, (match, lang, code) => {
        const id = '___CODEBLOCK_' + codeBlocks.length + '___';
        const escapedCode = escapeHtml(code.trim());
        const langLabel = lang ? '<span class="code-lang">' + escapeHtml(lang) + '</span>' : '<span class="code-lang">código</span>';
        codeBlocks.push(
            '<div class="code-block-wrapper">' +
                '<div class="code-header">' +
                    langLabel +
                    '<button class="copy-code-btn" onclick="window.copyCode(this)">Copiar</button>' +
                '</div>' +
                '<pre><code>' + escapedCode + '</code></pre>' +
            '</div>'
        );
        return id;
    });

    // 2. Escapar HTML del texto general
    processed = escapeHtml(processed);

    // 3. Codigo inline
    processed = processed.replace(/`([^`]+)`/g, '<code class="inline-code">$1</code>');

    // 4. Encabezados
    processed = processed.replace(/^### (.*$)/gim, '<h4>$1</h4>');
    processed = processed.replace(/^## (.*$)/gim, '<h3>$1</h3>');
    processed = processed.replace(/^# (.*$)/gim, '<h2>$1</h2>');

    // 5. Negrita e italica
    processed = processed.replace(/\*\*([^*]+)\*\*/g, '<strong>$1</strong>');
    processed = processed.replace(/\*([^*]+)\*/g, '<em>$1</em>');
    processed = processed.replace(/__([^_]+)__/g, '<strong>$1</strong>');

    // 6. Citas
    processed = processed.replace(/^&gt; (.*$)/gim, '<blockquote>$1</blockquote>');

    // 7. Lineas horizontales
    processed = processed.replace(/^---$/gim, '<hr>');

    // 8. Listas simples
    processed = processed.replace(/^\s*[-*]\s+(.*)$/gim, '<li>$1</li>');
    processed = processed.replace(/^\s*\d+\.\s+(.*)$/gim, '<li>$1</li>');

    // 9. Links markdown [texto](url)
    processed = processed.replace(/\[(.*?)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');

    // 10. Parrafos y saltos de linea
    processed = processed.replace(/\n{2,}/g, '</p><p>');
    processed = processed.replace(/\n/g, '<br>');
    processed = '<p>' + processed + '</p>';

    // Limpieza
    processed = processed.replace(/<p><\/p>/g, '');
    processed = processed.replace(/<p>(<h[2-4]>.*?<\/h[2-4]>)<\/p>/g, '$1');
    processed = processed.replace(/<p>(<div class="code-block-wrapper">[\s\S]*?<\/div>)<\/p>/g, '$1');
    processed = processed.replace(/<p>(<blockquote>[\s\S]*?<\/blockquote>)<\/p>/g, '$1');

    // 11. Restaurar bloques de codigo
    codeBlocks.forEach((block, idx) => {
        processed = processed.replace('___CODEBLOCK_' + idx + '___', block);
    });

    return processed;
}

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

    if (sender === 'assistant') {
        contentDiv.innerHTML = renderMarkdown(text);
        if (navigator.vibrate && autoPlay) {
            navigator.vibrate([40, 60, 40]);
        }
    } else {
        const p = document.createElement('p');
        p.innerText = text;
        contentDiv.appendChild(p);
    }

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
            body: JSON.stringify({ 
                text: text,
                chat_id: activeChatId || ''
            })
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
    if (activeChatId) {
        formData.append('chat_id', activeChatId);
    }

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
    if (navigator.vibrate) navigator.vibrate(35);
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

// Control de Mute Sonido en PC
const pcSoundToggleBtn = document.getElementById('pc-sound-toggle-btn');
const pcSoundOnIcon = document.getElementById('pc-sound-on-icon');
const pcSoundOffIcon = document.getElementById('pc-sound-off-icon');
let isPcSoundMuted = false;

function updatePcSoundUI(muted) {
    isPcSoundMuted = !!muted;
    if (!pcSoundToggleBtn) return;
    if (isPcSoundMuted) {
        pcSoundToggleBtn.classList.add('muted');
        pcSoundToggleBtn.title = 'Audio en PC silenciado (toca para activar)';
        if (pcSoundOnIcon) pcSoundOnIcon.style.display = 'none';
        if (pcSoundOffIcon) pcSoundOffIcon.style.display = 'inline-block';
    } else {
        pcSoundToggleBtn.classList.remove('muted');
        pcSoundToggleBtn.title = 'Silenciar audio en PC';
        if (pcSoundOnIcon) pcSoundOnIcon.style.display = 'inline-block';
        if (pcSoundOffIcon) pcSoundOffIcon.style.display = 'none';
    }
}

if (pcSoundToggleBtn) {
    pcSoundToggleBtn.addEventListener('click', async () => {
        try {
            const resp = await fetch('/api/toggle_pc_sound', { method: 'POST' });
            const data = await resp.json();
            if (data && data.success) {
                updatePcSoundUI(data.pc_audio_muted);
            }
        } catch (e) {
            console.error('Error al conmutar sonido en PC:', e);
        }
    });
}

// Selector de Chats de Antigravity
const chatSelectorBtn = document.getElementById('chat-selector-btn');
const currentChatTitle = document.getElementById('current-chat-title');
const chatsModal = document.getElementById('chats-modal');
const chatsModalOverlay = document.getElementById('chats-modal-overlay');
const chatsModalClose = document.getElementById('chats-modal-close');
const chatsList = document.getElementById('chats-list');
const prevChatBtn = document.getElementById('prev-chat-btn');
const nextChatBtn = document.getElementById('next-chat-btn');
let activeChatId = '';

function openChatsModal() {
    if (!chatsModal) return;
    chatsModal.classList.remove('hidden');
    loadChatsList();
}

function closeChatsModal() {
    if (!chatsModal) return;
    chatsModal.classList.add('hidden');
}

async function loadChatsList() {
    if (!chatsList) return;
    chatsList.innerHTML = '<div class="loading-chats">Buscando chats abiertos...</div>';
    try {
        const resp = await fetch('/api/chats');
        const data = await resp.json();
        const chats = data.chats || [];
        activeChatId = data.current_id || '';

        if (chats.length === 0) {
            chatsList.innerHTML = '<div class="empty-chats">No se detectaron chats abiertos</div>';
            return;
        }

        chatsList.innerHTML = '';
        chats.forEach(chat => {
            const item = document.createElement('div');
            item.className = `chat-item ${chat.active ? 'active' : ''}`;
            
            let badgeHtml = chat.active ? '<span class="chat-item-badge">Activo</span>' : '';
            item.innerHTML = `
                <span class="chat-item-title">${chat.title}</span>
                ${badgeHtml}
            `;

            if (chat.active && currentChatTitle) {
                currentChatTitle.innerText = chat.title;
            }

            item.addEventListener('click', () => {
                switchAntigravityChat(chat.id);
            });

            chatsList.appendChild(item);
        });
    } catch (err) {
        chatsList.innerHTML = '<div class="empty-chats">Error conectando con el servidor</div>';
    }
}

async function switchAntigravityChat(target) {
    closeChatsModal();
    micStatusLabel.innerText = 'Cambiando de chat...';
    try {
        const resp = await fetch('/api/switch_chat', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ target: target })
        });
        const res = await resp.json();
        if (res.success) {
            if (currentChatTitle) {
                currentChatTitle.innerText = res.title;
            }
            if (res.id) {
                activeChatId = res.id;
            }
            currentSyncIndex = 0;
            appendMessage('assistant', `Cambiado al chat: ${res.title}`, null, null, false);
            micStatusLabel.innerText = 'Toca para hablar';
            syncWithAntigravity();
        } else {
            alert(`No se pudo cambiar de chat: ${res.error || 'error desconocido'}`);
            micStatusLabel.innerText = 'Toca para hablar';
        }
    } catch (err) {
        alert('Error comunicando con TARS para cambiar de chat');
        micStatusLabel.innerText = 'Toca para hablar';
    }
}

async function loadInitialChatTitle() {
    try {
        const resp = await fetch('/api/chats');
        const data = await resp.json();
        activeChatId = data.current_id || '';
        const chats = data.chats || [];
        const activeChat = chats.find(c => c.active || c.id === activeChatId);
        if (activeChat && currentChatTitle) {
            currentChatTitle.innerText = activeChat.title;
        }
    } catch (e) {
        // Silencioso
    }
}

if (chatSelectorBtn) {
    chatSelectorBtn.addEventListener('click', openChatsModal);
}
if (chatsModalClose) {
    chatsModalClose.addEventListener('click', closeChatsModal);
}
if (chatsModalOverlay) {
    chatsModalOverlay.addEventListener('click', closeChatsModal);
}
if (prevChatBtn) {
    prevChatBtn.addEventListener('click', () => switchAntigravityChat('anterior'));
}
if (nextChatBtn) {
    nextChatBtn.addEventListener('click', () => switchAntigravityChat('siguiente'));
}

// Sincronizacion en tiempo real con la sesion activa de Antigravity
let currentSyncIndex = 0;

async function syncWithAntigravity() {
    try {
        const resp = await fetch(`/api/sync?last_index=${currentSyncIndex}&chat_id=${encodeURIComponent(activeChatId)}`);
        const data = await resp.json();

        if (data.chat_id) {
            activeChatId = data.chat_id;
        }

        if (typeof data.pc_audio_muted === 'boolean' && data.pc_audio_muted !== isPcSoundMuted) {
            updatePcSoundUI(data.pc_audio_muted);
        }

        if (data.processing_info && data.processing_info.is_processing) {
            updateProcessingBubble(data.processing_info);
            micStatusLabel.innerText = "⏳ " + (data.processing_info.tool_action || "Pensando...");
        } else {
            removeProcessingBubble();
            if (!isRecording && micStatusLabel.innerText.startsWith("⏳ ")) {
                micStatusLabel.innerText = 'Toca para hablar';
            }
        }

        if (data.chat_changed) {
            // Cambio de chat detectado
            loadInitialChatTitle();
            currentSyncIndex = data.step_index;
            if (data.content) {
                appendMessage('assistant', data.content, data.media, data.audio_url, false);
            }
        } else if (data.has_new && data.step_index > currentSyncIndex) {
            removeProcessingBubble();
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

loadInitialChatTitle();
setInterval(syncWithAntigravity, 1500);
syncWithAntigravity();
