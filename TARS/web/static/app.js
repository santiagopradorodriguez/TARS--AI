
function updateProcessingBubble(info) {
    let bubble = document.getElementById('processing-bubble');
    if (!bubble) {
        bubble = document.createElement('div');
        bubble.id = 'processing-bubble';
        bubble.className = 'message assistant processing-card';
        chatContainer.appendChild(bubble);
    }

    const stepsCount = info.steps_count || 1;
    const actionText = escapeHtml(info.tool_action || info.thought || 'Procesando...');
    const detailHtml = info.tool_detail ? `<div class="proc-detail">${escapeHtml(info.tool_detail)}</div>` : '';

    let stepsListHtml = '';
    if (Array.isArray(info.recent_steps) && info.recent_steps.length > 0) {
        const items = info.recent_steps.map((st, idx) => {
            const isLast = (idx === info.recent_steps.length - 1);
            const icon = isLast ? '⏳' : '✅';
            return `<div class="proc-step-item ${isLast ? 'current' : 'done'}">${icon} ${escapeHtml(st)}</div>`;
        }).join('');
        stepsListHtml = `<div class="processing-thought-box">${items}</div>`;
    } else {
        stepsListHtml = `<div class="processing-thought-box">⏳ ${actionText}</div>`;
    }

    bubble.innerHTML = `
        <div class="processing-card-header">
            <div class="processing-header-left">
                <span class="processing-pulse"></span>
                <span class="processing-title">🛠️ Laburando (Paso ${stepsCount})...</span>
            </div>
            <button class="proc-stop-inline-btn" onclick="window.cancelCurrentProcessing()" title="Cortar procesamiento de inmediato">
                <svg viewBox="0 0 24 24" width="13" height="13" fill="currentColor"><path d="M6 6h12v12H6z"/></svg>
                Cortar
            </button>
        </div>
        ${stepsListHtml}
        <div class="processing-tool-box">
            <span class="proc-badge">Ahora</span>
            <span>${actionText}</span>
            ${detailHtml}
        </div>
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
    processed = processed.replace(/\[(.*?)\]\(file:\/\/(\/[^\)\s#]+)(?:#[^\)\s]*)?\)/g, (m, label, fpath) => {
        return `<a href="/api/download?path=${encodeURIComponent(fpath)}" download class="inline-file-link" title="Descargar archivo">${label} ⬇</a>`;
    });

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

// Desbloquear audio en movil y mantener viva la ejecucion en segundo plano (con Chrome minimizado)
let audioUnlocked = false;
let bgKeepAliveAudio = null;

function updateMediaSessionNotification(textPreview) {
    if ('mediaSession' in navigator) {
        try {
            const chatName = (typeof currentChatTitle !== 'undefined' && currentChatTitle && currentChatTitle.innerText)
                ? currentChatTitle.innerText
                : 'Antigravity';
            navigator.mediaSession.metadata = new MediaMetadata({
                title: textPreview || 'TARS Conectado en segundo plano',
                artist: `🤖 TARS • ${chatName}`,
                album: 'Antigravity Móvil',
                artwork: [
                    { src: '/static/icon-192.png', sizes: '192x192', type: 'image/png' },
                    { src: '/static/icon-512.png', sizes: '512x512', type: 'image/png' }
                ]
            });
        } catch (e) {}
    }
}

function unlockMobileAudio() {
    if (!audioUnlocked) {
        // WAV silencioso de 1 segundo en loop para que Android no congele la pestaña al salir de Chrome
        bgKeepAliveAudio = new Audio("data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA");
        bgKeepAliveAudio.loop = true;
        bgKeepAliveAudio.volume = 0.01;
        bgKeepAliveAudio.play().then(() => {
            audioUnlocked = true;
            updateMediaSessionNotification('Sistemas listos • Escuchando respuestas');
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

function clearUserCancelChips() {
    document.querySelectorAll('.user-cancel-chip').forEach(btn => btn.remove());
}

function appendMessage(sender, text, media = null, audioUrl = null, autoPlay = true) {
    if (sender === 'assistant') {
        clearUserCancelChips();
    }

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
        clearUserCancelChips();
        const p = document.createElement('p');
        p.innerText = text;
        contentDiv.appendChild(p);

        const cancelChip = document.createElement('button');
        cancelChip.className = 'user-cancel-chip';
        cancelChip.innerHTML = `
            <svg viewBox="0 0 24 24" width="12" height="12" fill="currentColor"><path d="M6 6h12v12H6z"/></svg>
            <span>Cortar envío / IA</span>
        `;
        cancelChip.onclick = (e) => {
            e.stopPropagation();
            window.cancelCurrentProcessing();
        };
        contentDiv.appendChild(cancelChip);
    }

    const mediaList = Array.isArray(media) ? [...media] : [];
    if (sender === 'assistant' && text) {
        const existingNames = new Set(mediaList.map(m => m && m.name).filter(Boolean));
        const fileLinkRe = /file:\/\/(\/[^\)\s#"<>`]+)/g;
        let m;
        while ((m = fileLinkRe.exec(text)) !== null) {
            const rawP = decodeURIComponent(m[1]).split('#')[0].trim();
            const fname = rawP.split('/').pop();
            if (fname && !existingNames.has(fname)) {
                existingNames.add(fname);
                mediaList.push({
                    type: 'file',
                    url: `/api/download?path=${encodeURIComponent(rawP)}`,
                    name: fname
                });
            }
        }
    }

    if (mediaList.length > 0) {
        const mediaContainer = document.createElement('div');
        mediaContainer.className = 'media-container';

        mediaList.forEach(item => {
            if (item.type === 'image') {
                const img = document.createElement('img');
                img.src = item.url;
                img.className = 'media-image';
                img.onclick = () => window.open(item.url, '_blank');
                mediaContainer.appendChild(img);
            } else if (item.type === 'file') {
                const fname = item.name || 'archivo';
                const isAudioFile = /\.(wav|mp3|ogg|m4a|flac)$/i.test(fname);
                const wrapper = document.createElement('div');
                wrapper.style.display = 'flex';
                wrapper.style.flexDirection = 'column';
                wrapper.style.gap = '6px';

                if (isAudioFile) {
                    const audioEl = document.createElement('audio');
                    audioEl.controls = true;
                    audioEl.preload = 'none';
                    audioEl.src = item.url;
                    audioEl.style.width = '100%';
                    audioEl.style.height = '36px';
                    wrapper.appendChild(audioEl);
                }

                const a = document.createElement('a');
                a.href = item.url;
                a.className = 'file-card';
                a.download = fname;
                a.innerHTML = `
                    <div class="file-info">
                        <svg viewBox="0 0 24 24" width="18" height="18" fill="currentColor">
                            <path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/>
                        </svg>
                        <span class="file-name">Descargar ${fname}</span>
                    </div>
                    <svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor">
                        <path d="M19 9h-4V3H9v6H5l7 7 7-7zM5 18v2h14v-2H5z"/>
                    </svg>
                `;
                wrapper.appendChild(a);
                mediaContainer.appendChild(wrapper);
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

        // Auto-reproducir por voz si corresponde y la voz en celular no está silenciada
        if (sender === 'assistant' && autoPlay && !isMobileVoiceMuted) {
            playAudioUrl(audioUrl, audioBtn);
        }
    }

    msgDiv.appendChild(contentDiv);
    chatContainer.appendChild(msgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

// ===== MANEJO DE ARCHIVOS Y DOCUMENTOS ADJUNTOS =====
const attachBtn = document.getElementById('attach-btn');
const fileInput = document.getElementById('file-input');
const attachmentPreviewBar = document.getElementById('attachment-preview-bar');
let pendingAttachments = [];

function renderAttachmentPreviews() {
    if (!attachmentPreviewBar) return;
    if (pendingAttachments.length === 0) {
        attachmentPreviewBar.innerHTML = '';
        attachmentPreviewBar.classList.add('hidden');
        return;
    }
    attachmentPreviewBar.classList.remove('hidden');
    attachmentPreviewBar.innerHTML = '';
    pendingAttachments.forEach((file, index) => {
        const chip = document.createElement('div');
        chip.className = 'attachment-chip';

        if (file.type && file.type.startsWith('image/')) {
            const img = document.createElement('img');
            img.className = 'attachment-chip-thumb';
            img.src = URL.createObjectURL(file);
            chip.appendChild(img);
        } else {
            const icon = document.createElement('span');
            icon.className = 'attachment-chip-icon';
            icon.innerHTML = `<svg viewBox="0 0 24 24" width="16" height="16" fill="currentColor"><path d="M14 2H6c-1.1 0-1.99.9-1.99 2L4 20c0 1.1.89 2 1.99 2H18c1.1 0 2-.9 2-2V8l-6-6zm2 16H8v-2h8v2zm0-4H8v-2h8v2zm-3-5V3.5L18.5 9H13z"/></svg>`;
            chip.appendChild(icon);
        }

        const name = document.createElement('span');
        name.className = 'attachment-chip-name';
        name.innerText = file.name;
        chip.appendChild(name);

        const removeBtn = document.createElement('button');
        removeBtn.className = 'attachment-chip-remove';
        removeBtn.innerHTML = '&times;';
        removeBtn.addEventListener('click', (e) => {
            e.stopPropagation();
            pendingAttachments.splice(index, 1);
            renderAttachmentPreviews();
        });
        chip.appendChild(removeBtn);

        attachmentPreviewBar.appendChild(chip);
    });
}

if (attachBtn && fileInput) {
    attachBtn.addEventListener('click', () => fileInput.click());
    fileInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            for (const f of e.target.files) {
                pendingAttachments.push(f);
            }
            renderAttachmentPreviews();
            fileInput.value = '';
        }
    });
}

// ===== CONTROL DE CANCELACION DE GRABACION Y PROCESAMIENTO DE IA =====
const cancelProcBtn = document.getElementById('cancel-proc-btn');
const cancelProcLabel = document.getElementById('cancel-proc-label');
let recordingCancelled = false;
let activeFetchController = null;

window.cancelCurrentProcessing = async function() {
    if (navigator.vibrate) navigator.vibrate([80, 40, 80]);

    // 1. Si estaba grabando audio por micrófono: descartar sin enviar
    if (isRecording && mediaRecorder) {
        recordingCancelled = true;
        isRecording = false;
        micBtn.classList.remove('recording');
        if (cancelProcLabel) cancelProcLabel.innerText = 'Cortar';
        if (cancelProcBtn) cancelProcBtn.classList.remove('active-danger');
        micStatusLabel.innerText = '🛑 Audio cancelado (no enviado)';
        try {
            mediaRecorder.stop();
        } catch (e) {}
        showWhatsAppToast('🛑 Grabación descartada', 'El mensaje de voz fue cancelado y no se envió.');
        return;
    }

    // 2. Si había un envío o transcripción en curso: abortarlo en cliente y servidor
    if (activeFetchController) {
        try {
            activeFetchController.abort();
        } catch (e) {}
        activeFetchController = null;
    }

    // 3. Detener voz actual y limpiar burbuja de pensamiento
    stopCurrentAudio();
    removeProcessingBubble();
    clearUserCancelChips();
    if (cancelProcBtn) cancelProcBtn.classList.remove('active-danger');
    if (cancelProcLabel) cancelProcLabel.innerText = 'Cortar';
    micStatusLabel.innerText = '🛑 Cortando procesamiento en PC...';

    try {
        await fetch('/api/cancel', { method: 'POST' });
        micStatusLabel.innerText = '🛑 Procesamiento detenido';
        showWhatsAppToast('🛑 Procesamiento cortado', 'Se detuvo la ejecución en Antigravity IDE.');
        setTimeout(() => {
            if (!isRecording && micStatusLabel.innerText.includes('detenido')) {
                micStatusLabel.innerText = 'Toca para hablar';
            }
        }, 2500);
    } catch (e) {
        micStatusLabel.innerText = 'Toca para hablar';
    }
};

if (cancelProcBtn) {
    cancelProcBtn.addEventListener('click', (e) => {
        e.preventDefault();
        window.cancelCurrentProcessing();
    });
}

async function sendTextMessage(text) {
    const trimmed = text.trim();
    if (!trimmed && pendingAttachments.length === 0) return;

    const filesToSend = [...pendingAttachments];
    pendingAttachments = [];
    renderAttachmentPreviews();

    // Crear previews en la burbuja de chat del usuario
    const userMedia = filesToSend.map(f => {
        if (f.type && f.type.startsWith('image/')) {
            return { type: 'image', url: URL.createObjectURL(f), name: f.name };
        }
        return { type: 'file', url: '#', name: f.name };
    });

    const userTextDisplay = trimmed || (filesToSend.length > 0 ? (filesToSend.length === 1 ? `[Archivo adjunto: ${filesToSend[0].name}]` : `[${filesToSend.length} archivos adjuntos]`) : '');
    appendMessage('user', userTextDisplay, userMedia.length > 0 ? userMedia : null);
    textInput.value = '';

    if (cancelProcBtn) cancelProcBtn.classList.add('active-danger');
    if (cancelProcLabel) cancelProcLabel.innerText = 'Cortar IA';

    activeFetchController = new AbortController();
    try {
        let resp;
        if (filesToSend.length > 0) {
            const formData = new FormData();
            formData.append('text', trimmed);
            formData.append('chat_id', activeChatId || '');
            filesToSend.forEach(f => formData.append('files', f));
            resp = await fetch('/api/chat', {
                method: 'POST',
                body: formData,
                signal: activeFetchController.signal
            });
        } else {
            resp = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ 
                    text: trimmed,
                    chat_id: activeChatId || ''
                }),
                signal: activeFetchController.signal
            });
        }
        activeFetchController = null;
        const data = await resp.json();
        if (data.sent_to_ide) {
            micStatusLabel.innerText = 'Antigravity procesando en PC...';
        } else if (data.reply) {
            appendMessage('assistant', data.reply, data.media, data.audio_url);
            if (cancelProcBtn) cancelProcBtn.classList.remove('active-danger');
        }
    } catch (err) {
        activeFetchController = null;
        if (err && err.name === 'AbortError') return;
        appendMessage('assistant', 'Error de conexión al enviar el mensaje.');
    }
}

async function sendAudioBlob(blob) {
    const filesToSend = [...pendingAttachments];
    pendingAttachments = [];
    renderAttachmentPreviews();

    const userMedia = filesToSend.map(f => {
        if (f.type && f.type.startsWith('image/')) {
            return { type: 'image', url: URL.createObjectURL(f), name: f.name };
        }
        return { type: 'file', url: '#', name: f.name };
    });

    appendMessage('user', '[Mensaje de voz enviado]', userMedia.length > 0 ? userMedia : null);

    const formData = new FormData();
    formData.append('audio', blob, 'voice.webm');
    if (activeChatId) {
        formData.append('chat_id', activeChatId);
    }
    filesToSend.forEach(f => formData.append('files', f));

    if (cancelProcBtn) cancelProcBtn.classList.add('active-danger');
    if (cancelProcLabel) cancelProcLabel.innerText = 'Cortar IA';

    activeFetchController = new AbortController();
    try {
        micStatusLabel.innerText = 'Transcribiendo... (toca Cortar para anular)';
        const resp = await fetch('/api/audio', {
            method: 'POST',
            body: formData,
            signal: activeFetchController.signal
        });
        activeFetchController = null;
        const data = await resp.json();

        if (data.user_text) {
            // Reemplazar mensaje de usuario con el texto transcripto
            const msgs = document.querySelectorAll('.message.user');
            if (msgs.length > 0) {
                const pEl = msgs[msgs.length - 1].querySelector('p');
                if (pEl) pEl.innerText = data.user_text;
            }
        }

        if (data.cancelled) {
            micStatusLabel.innerText = '🛑 Envío cancelado';
            return;
        }

        if (data.sent_to_ide) {
            // Inyectado a Antigravity IDE
            micStatusLabel.innerText = 'Antigravity procesando en PC...';
        } else if (data.reply) {
            appendMessage('assistant', data.reply, data.media, data.audio_url);
            micStatusLabel.innerText = 'Toca para hablar';
            if (cancelProcBtn) cancelProcBtn.classList.remove('active-danger');
        }
    } catch (err) {
        activeFetchController = null;
        if (err && err.name === 'AbortError') return;
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
        recordingCancelled = false;

        mediaRecorder.ondataavailable = (event) => {
            if (event.data.size > 0) {
                audioChunks.push(event.data);
            }
        };

        mediaRecorder.onstop = () => {
            stream.getTracks().forEach(track => track.stop());
            if (recordingCancelled) {
                audioChunks = [];
                recordingCancelled = false;
                return;
            }
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            if (audioChunks.length > 0) {
                sendAudioBlob(audioBlob);
            }
        };

        mediaRecorder.start();
        isRecording = true;
        recordStartTime = Date.now();
        micBtn.classList.add('recording');
        if (cancelProcBtn) cancelProcBtn.classList.add('active-danger');
        if (cancelProcLabel) cancelProcLabel.innerText = 'Cancelar';
        micStatusLabel.innerText = 'Escuchando... Toca mic para enviar o Cancelar';
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

// Control de Silencio de Voz en el Celular (desde la app y desde la notificación)
const mobileVoiceToggleBtn = document.getElementById('mobile-voice-toggle-btn');
const mobileVoiceOnIcon = document.getElementById('mobile-voice-on-icon');
const mobileVoiceOffIcon = document.getElementById('mobile-voice-off-icon');
const mobileVoiceLabel = document.getElementById('mobile-voice-label');
let isMobileVoiceMuted = localStorage.getItem('tars_mobile_voice_muted') === 'true';

function updateMobileVoiceUI(muted) {
    isMobileVoiceMuted = !!muted;
    localStorage.setItem('tars_mobile_voice_muted', isMobileVoiceMuted ? 'true' : 'false');
    if (isMobileVoiceMuted) {
        stopCurrentAudio();
    }
    if (!mobileVoiceToggleBtn) return;
    if (isMobileVoiceMuted) {
        mobileVoiceToggleBtn.classList.add('muted');
        mobileVoiceToggleBtn.title = 'Voz en celular silenciada (toca para activar)';
        if (mobileVoiceOnIcon) mobileVoiceOnIcon.style.display = 'none';
        if (mobileVoiceOffIcon) mobileVoiceOffIcon.style.display = 'inline-block';
        if (mobileVoiceLabel) mobileVoiceLabel.innerText = 'Mudo';
    } else {
        mobileVoiceToggleBtn.classList.remove('muted');
        mobileVoiceToggleBtn.title = 'Silenciar voz en el celular';
        if (mobileVoiceOnIcon) mobileVoiceOnIcon.style.display = 'inline-block';
        if (mobileVoiceOffIcon) mobileVoiceOffIcon.style.display = 'none';
        if (mobileVoiceLabel) mobileVoiceLabel.innerText = 'Voz';
    }
}
updateMobileVoiceUI(isMobileVoiceMuted);

if (mobileVoiceToggleBtn) {
    mobileVoiceToggleBtn.addEventListener('click', async () => {
        if (navigator.vibrate) navigator.vibrate(40);
        const nextMuted = !isMobileVoiceMuted;
        updateMobileVoiceUI(nextMuted);
        showWhatsAppToast(
            nextMuted ? '🔇 Voz del celular desactivada' : '🔊 Voz del celular activada',
            nextMuted ? 'No te hablaré en voz alta cuando lleguen mensajes.' : 'Volveré a leerte las respuestas por voz.'
        );
        try {
            await fetch('/api/toggle_mobile_voice', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify({ muted: nextMuted })
            });
        } catch (e) {}
    });
}

if ('serviceWorker' in navigator) {
    window.addEventListener('load', () => {
        navigator.serviceWorker.register('/sw.js').then((reg) => {
            console.log('[TARS PWA] Service Worker registrado:', reg.scope);
        }).catch((err) => {
            console.warn('[TARS PWA] Error registrando SW:', err);
        });
    });

    navigator.serviceWorker.addEventListener('message', (event) => {
        if (event.data && event.data.type === 'SET_MOBILE_VOICE_MUTE') {
            updateMobileVoiceUI(Boolean(event.data.muted));
        }
    });
}

// Manejador de instalacion de PWA en celular
let deferredInstallPrompt = null;
const pwaInstallBtn = document.getElementById('pwa-install-btn');

// Si ya esta corriendo dentro de la app instalada (modo standalone), ocultamos el boton
const isRunningStandalone = window.matchMedia('(display-mode: standalone)').matches ||
                            window.navigator.standalone === true ||
                            document.referrer.includes('android-app://');

if (pwaInstallBtn && isRunningStandalone) {
    pwaInstallBtn.style.display = 'none';
}

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    if (pwaInstallBtn && !isRunningStandalone) {
        pwaInstallBtn.style.display = 'inline-flex';
    }
});

if (pwaInstallBtn) {
    pwaInstallBtn.addEventListener('click', async () => {
        if (deferredInstallPrompt) {
            try {
                deferredInstallPrompt.prompt();
                const choiceResult = await deferredInstallPrompt.userChoice;
                if (choiceResult && choiceResult.outcome === 'accepted') {
                    pwaInstallBtn.style.display = 'none';
                }
            } catch (err) {
                console.warn('[PWA Install Error]', err);
            }
            deferredInstallPrompt = null;
        } else {
            const isIOS = /iPad|iPhone|iPod/.test(navigator.userAgent) && !window.MSStream;
            if (isIOS) {
                alert('📱 Para instalar TARS en iPhone / iPad:\n\n1. Tocá el botón "Compartir" de Safari (cuadrado con flecha hacia arriba).\n2. Elegí "Agregar a la pantalla de inicio".');
                return;
            }

            try {
                const res = await fetch('/api/tunnel_url');
                const tdata = await res.json();
                if (tdata.tunnel_url && !window.location.origin.includes('trycloudflare.com')) {
                    if (confirm('🔒 Google Chrome en Android bloquea compilar Apps desde IPs privadas con certificado local.\n\n¿Querés abrir TARS con el enlace seguro de Cloudflare para instalar la App directamente en 1 clic?')) {
                        window.location.href = tdata.tunnel_url;
                        return;
                    }
                }
            } catch (err) {}

            alert('📱 Para instalar TARS en tu celular:\n\nOpción 1 (Chrome): Tocá los 3 puntitos (⋮) > "Agregar a la pantalla principal".\n\nOpción 2 (Samsung): Abrí esta página en el navegador "Samsung Internet" y tocalo desde la barra para instalarlo.');
        }
    });
}

window.addEventListener('appinstalled', () => {
    if (pwaInstallBtn) pwaInstallBtn.style.display = 'none';
    deferredInstallPrompt = null;
});

if ('mediaSession' in navigator) {
    try {
        navigator.mediaSession.setActionHandler('pause', () => {
            stopCurrentAudio();
        });
        navigator.mediaSession.setActionHandler('stop', () => {
            stopCurrentAudio();
        });
    } catch (e) {}
}

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
            const msg = data.error || 'No se detectaron chats abiertos';
            chatsList.innerHTML = `<div class="empty-chats">${msg}</div>`;
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

function renderChatHistory(messages, lastStepIndex) {
    if (!chatContainer || !Array.isArray(messages)) return;
    chatContainer.innerHTML = '';
    renderedStepIndices.clear();

    if (messages.length === 0) {
        const title = currentChatTitle ? currentChatTitle.innerText : 'Conversacion';
        appendMessage('assistant', `Chat activo: ${title}. Puedes hablar o escribir para continuar.`, null, null, false);
        currentSyncIndex = 0;
        return;
    }

    messages.forEach(msg => {
        const isAssistant = (msg.role === 'assistant');
        appendMessage(
            isAssistant ? 'assistant' : 'user',
            msg.content,
            msg.media || null,
            null,
            false
        );
        if (msg.step_index) {
            renderedStepIndices.add(msg.step_index);
        }
    });

    if (lastStepIndex) {
        currentSyncIndex = lastStepIndex;
    }
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

let isLoadingHistory = false;
async function loadChatHistory(chatId) {
    if (!chatId || isLoadingHistory) return;
    isLoadingHistory = true;
    try {
        const resp = await fetch(`/api/chat_history?chat_id=${encodeURIComponent(chatId)}&limit=10`);
        const data = await resp.json();
        if (data && Array.isArray(data.messages)) {
            renderChatHistory(data.messages, data.last_step_index);
        }
    } catch (e) {
        console.warn('[TARS Web] Error cargando historial:', e);
    } finally {
        isLoadingHistory = false;
    }
}

async function switchAntigravityChat(target) {
    closeChatsModal();
    if (chatContainer) {
        chatContainer.innerHTML = `
            <div class="chat-loading-placeholder">
                <div class="loading-spinner"></div>
                <span>Cambiando chats, por favor espere...</span>
            </div>
        `;
    }
    if (micStatusLabel) {
        micStatusLabel.innerText = 'Cambiando chats, por favor espere...';
    }
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

            if (Array.isArray(res.messages) && res.messages.length > 0) {
                renderChatHistory(res.messages, res.last_step_index);
            } else {
                await loadChatHistory(activeChatId);
            }

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
        if (activeChatId) {
            await loadChatHistory(activeChatId);
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

// ===== SELECTOR DE MODELOS DE IA DE ANTIGRAVITY =====
const modelSelectorBtn = document.getElementById('model-selector-btn');
const currentModelTitle = document.getElementById('current-model-title');
const modelsModal = document.getElementById('models-modal');
const modelsModalOverlay = document.getElementById('models-modal-overlay');
const modelsModalClose = document.getElementById('models-modal-close');
const modelsList = document.getElementById('models-list');

function formatShortModelName(fullName) {
    if (!fullName) return 'Modelo IA';
    return fullName
        .replace(/^Gemini\s+/i, 'G-')
        .replace(/^Claude\s+/i, '')
        .replace(/\(Thinking\)/i, '')
        .replace(/\s+/g, ' ')
        .trim();
}

function updateCurrentModelUI(modelStr) {
    if (modelStr && currentModelTitle) {
        currentModelTitle.innerText = formatShortModelName(modelStr);
        if (modelSelectorBtn) {
            modelSelectorBtn.title = `Modelo actual: ${modelStr}`;
        }
    }
}

function openModelsModal() {
    if (!modelsModal) return;
    modelsModal.classList.remove('hidden');
    loadModelsList();
}

function closeModelsModal() {
    if (!modelsModal) return;
    modelsModal.classList.add('hidden');
}

async function loadModelsList() {
    if (!modelsList) return;
    modelsList.innerHTML = '<div class="loading-chats">Consultando modelos disponibles...</div>';
    try {
        const resp = await fetch('/api/models');
        const data = await resp.json();
        const models = data.models || [];
        if (data.current_model) {
            updateCurrentModelUI(data.current_model);
        }
        if (models.length === 0) {
            modelsList.innerHTML = '<div class="empty-chats">No se pudieron leer los modelos</div>';
            return;
        }
        modelsList.innerHTML = '';
        models.forEach(m => {
            const card = document.createElement('div');
            card.className = `model-item ${m.active ? 'active' : ''}`;

            const top = document.createElement('div');
            top.className = 'model-item-top';
            let statusBadge = m.active
                ? '<span class="chat-item-badge">En uso</span>'
                : (m.effort ? `<span style="font-size:0.75rem;color:var(--text-muted);">${m.effort}</span>` : '');
            top.innerHTML = `
                <span class="model-item-name">${m.name}</span>
                ${statusBadge}
            `;
            card.appendChild(top);

            if (m.has_effort) {
                const pills = document.createElement('div');
                pills.className = 'effort-pills';
                ['Low', 'Medium', 'High'].forEach(eff => {
                    const pill = document.createElement('button');
                    pill.className = `effort-pill ${(m.active && (data.current_model || '').toLowerCase().includes(eff.toLowerCase())) || (!m.active && m.effort === eff) ? 'active' : ''}`;
                    pill.innerText = eff === 'Low' ? 'Rápido (Low)' : (eff === 'Medium' ? 'Medio (Med)' : 'Máximo (High)');
                    pill.addEventListener('click', (e) => {
                        e.stopPropagation();
                        switchAntigravityModel(m.name, eff);
                    });
                    pills.appendChild(pill);
                });
                card.appendChild(pills);
            }

            card.addEventListener('click', () => {
                switchAntigravityModel(m.name, m.effort || null);
            });
            modelsList.appendChild(card);
        });
    } catch (e) {
        modelsList.innerHTML = '<div class="empty-chats">Error conectando con el servidor</div>';
    }
}

async function switchAntigravityModel(modelName, effort = null) {
    closeModelsModal();
    micStatusLabel.innerText = `Cambiando a ${modelName}...`;
    try {
        const resp = await fetch('/api/switch_model', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ model: modelName, effort: effort })
        });
        const res = await resp.json();
        if (res && res.success) {
            const finalName = res.current_model || (effort ? `${modelName} ${effort}` : modelName);
            updateCurrentModelUI(finalName);
            showWhatsAppToast('🧠 Modelo IA actualizado', `Ahora estás usando: ${finalName}`);
            micStatusLabel.innerText = 'Toca para hablar';
        } else {
            alert('No se pudo cambiar el modelo');
            micStatusLabel.innerText = 'Toca para hablar';
        }
    } catch (e) {
        alert('Error cambiando el modelo en la PC');
        micStatusLabel.innerText = 'Toca para hablar';
    }
}

if (modelSelectorBtn) {
    modelSelectorBtn.addEventListener('click', openModelsModal);
}
if (modelsModalClose) {
    modelsModalClose.addEventListener('click', closeModelsModal);
}
if (modelsModalOverlay) {
    modelsModalOverlay.addEventListener('click', closeModelsModal);
}

// ===== SELECTOR MULTI-PC (TAILSCALE / LAN) =====
const pcSelectorBtn = document.getElementById('pc-selector-btn');
const currentPcTitle = document.getElementById('current-pc-title');
const pcsModal = document.getElementById('pcs-modal');
const pcsModalOverlay = document.getElementById('pcs-modal-overlay');
const pcsModalClose = document.getElementById('pcs-modal-close');
const pcsList = document.getElementById('pcs-list');
const customPcNameInput = document.getElementById('custom-pc-name');
const customPcIpInput = document.getElementById('custom-pc-ip');
const addCustomPcBtn = document.getElementById('add-custom-pc-btn');

let activePcId = 'local';
let activePcName = 'PC';

function updateActivePcUI(pcInfo) {
    if (!pcInfo) return;
    activePcId = pcInfo.id || 'local';
    activePcName = pcInfo.name || 'PC';
    if (currentPcTitle) {
        currentPcTitle.innerText = activePcName;
    }
    if (pcSelectorBtn) {
        if (pcInfo.is_local) {
            pcSelectorBtn.classList.remove('remote-active');
        } else {
            pcSelectorBtn.classList.add('remote-active');
        }
        pcSelectorBtn.title = `PC activa: ${activePcName} (${pcInfo.ip || 'local'})`;
    }
}

function openPcsModal() {
    if (!pcsModal) return;
    pcsModal.classList.remove('hidden');
    loadPcsList();
}

function closePcsModal() {
    if (!pcsModal) return;
    pcsModal.classList.add('hidden');
}

async function loadPcsList() {
    if (!pcsList) return;
    pcsList.innerHTML = '<div class="loading-chats">Buscando tus PCs en Tailscale...</div>';
    try {
        const resp = await fetch('/api/pcs');
        const data = await resp.json();
        if (data.active_pc) {
            updateActivePcUI(data.active_pc);
        }
        const pcs = data.pcs || [];
        if (pcs.length === 0) {
            pcsList.innerHTML = '<div class="empty-chats">No se encontraron PCs</div>';
            return;
        }
        pcsList.innerHTML = '';
        pcs.forEach(pc => {
            const card = document.createElement('div');
            card.className = `pc-item ${pc.active ? 'active' : ''}`;

            const statusDotClass = pc.tars_online ? 'online' : (pc.online ? 'online' : 'offline');
            const statusLabel = pc.is_local
                ? 'Esta PC • En línea'
                : (pc.tars_online ? 'Tailscale • TARS Activo' : (pc.online ? 'Tailscale • En línea' : 'Desconectada'));

            const activeBadge = pc.active
                ? '<span class="chat-item-badge">Conectada</span>'
                : '';

            const directLinkHtml = (!pc.is_local && pc.direct_url)
                ? `<a href="${escapeHtml(pc.direct_url)}" target="_blank" rel="noopener" class="pc-direct-link" onclick="event.stopPropagation()" title="Abrir servidor web de esta PC directo">↗ Directo</a>`
                : '';

            card.innerHTML = `
                <div class="pc-item-left">
                    <div class="pc-item-title-row">
                        <span class="pc-status-dot ${statusDotClass}"></span>
                        <span class="pc-item-name">${escapeHtml(pc.name)}</span>
                    </div>
                    <div class="pc-item-sub">${escapeHtml(pc.ip)} • ${statusLabel}</div>
                </div>
                <div class="pc-item-right">
                    ${directLinkHtml}
                    ${activeBadge}
                </div>
            `;

            card.addEventListener('click', () => {
                selectTargetPc(pc);
            });
            pcsList.appendChild(card);
        });
    } catch (e) {
        pcsList.innerHTML = '<div class="empty-chats">Error consultando PCs disponibles</div>';
    }
}

async function selectTargetPc(pc) {
    closePcsModal();
    micStatusLabel.innerText = `Conectando con ${pc.name}...`;
    try {
        const resp = await fetch('/api/select_pc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({
                id: pc.id,
                ip: pc.ip,
                name: pc.name,
                hostname: pc.hostname
            })
        });
        const res = await resp.json();
        if (res && res.success) {
            updateActivePcUI(res.active_pc);
            if (navigator.vibrate) navigator.vibrate([40, 40, 60]);
            removeProcessingBubble();
            renderedStepIndices.clear();
            currentSyncIndex = 0;
            activeChatId = '';
            await loadInitialChatTitle();
            await syncWithAntigravity();
            showWhatsAppToast(
                `💻 Conectado a ${res.active_pc.name}`,
                `Ahora estás controlando Antigravity en ${res.active_pc.name} (${res.active_pc.ip})`
            );
            micStatusLabel.innerText = 'Toca para hablar';
        }
    } catch (e) {
        micStatusLabel.innerText = 'Error cambiando de PC';
    }
}

async function addCustomPc() {
    if (!customPcIpInput) return;
    const ipVal = customPcIpInput.value.trim();
    const nameVal = customPcNameInput ? customPcNameInput.value.trim() : '';
    if (!ipVal) return;
    try {
        const resp = await fetch('/api/add_pc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip: ipVal, name: nameVal })
        });
        const data = await resp.json();
        if (data && data.success) {
            customPcIpInput.value = '';
            if (customPcNameInput) customPcNameInput.value = '';
            if (data.active_pc) {
                updateActivePcUI(data.active_pc);
                renderedStepIndices.clear();
                currentSyncIndex = 0;
                activeChatId = '';
                loadInitialChatTitle();
                syncWithAntigravity();
            }
            closePcsModal();
            showWhatsAppToast(`💻 PC agregada`, `Conectado a ${data.active_pc ? data.active_pc.name : ipVal}`);
        }
    } catch (e) {}
}

if (pcSelectorBtn) {
    pcSelectorBtn.addEventListener('click', openPcsModal);
}
if (pcsModalClose) {
    pcsModalClose.addEventListener('click', closePcsModal);
}
if (pcsModalOverlay) {
    pcsModalOverlay.addEventListener('click', closePcsModal);
}
if (addCustomPcBtn) {
    addCustomPcBtn.addEventListener('click', addCustomPc);
}

// ===== SISTEMA DE NOTIFICACIONES PUSH REALES (ESTILO WHATSAPP CON PESTAÑA CERRADA) =====
const notifyToggleBtn = document.getElementById('notify-toggle-btn');
const notifyBtnLabel = document.getElementById('notify-btn-label');
const waToastBanner = document.getElementById('wa-toast-banner');
const waToastTitle = document.getElementById('wa-toast-title');
const waToastText = document.getElementById('wa-toast-text');

let swRegistration = null;
let waToastTimer = null;
let wakeLockSentinel = null;

function urlBase64ToUint8Array(base64String) {
    const padding = '='.repeat((4 - base64String.length % 4) % 4);
    const base64 = (base64String + padding).replace(/-/g, '+').replace(/_/g, '/');
    const rawData = window.atob(base64);
    const outputArray = new Uint8Array(rawData.length);
    for (let i = 0; i < rawData.length; ++i) {
        outputArray[i] = rawData.charCodeAt(i);
    }
    return outputArray;
}

async function setupWebPushSubscription() {
    if (!('serviceWorker' in navigator)) return false;
    try {
        swRegistration = await navigator.serviceWorker.register('/sw.js');
        await navigator.serviceWorker.ready;
        if (!('PushManager' in window)) return false;

        const keyResp = await fetch('/api/vapid_public_key');
        const keyData = await keyResp.json();
        if (!keyData.public_key) return false;

        let sub = await swRegistration.pushManager.getSubscription();
        if (!sub) {
            sub = await swRegistration.pushManager.subscribe({
                userVisibleOnly: true,
                applicationServerKey: urlBase64ToUint8Array(keyData.public_key)
            });
        }
        await fetch('/api/push_subscribe', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(sub)
        });
        isPushSubscribed = true;
        updateNotifyBtnUI(true);
        return true;
    } catch (e) {
        console.log('WebPush requiere HTTPS valido o app ntfy:', e);
        return false;
    }
}

let isPushSubscribed = false;

function updateNotifyBtnUI(pushActive = false) {
    if (!notifyToggleBtn) return;
    if (pushActive || ('Notification' in window && Notification.permission === 'granted')) {
        notifyToggleBtn.classList.add('active');
        if (notifyBtnLabel) notifyBtnLabel.innerText = 'ON';
    } else {
        notifyToggleBtn.classList.remove('active');
        if (notifyBtnLabel) notifyBtnLabel.innerText = 'OFF';
    }
}
updateNotifyBtnUI();
if ('Notification' in window && Notification.permission === 'granted') {
    setupWebPushSubscription();
}

function cleanPreviewText(raw) {
    if (!raw) return 'Nuevo mensaje recibido';
    return raw
        .replace(/```[\s\S]*?```/g, '[Código] ')
        .replace(/[*#_`~>]/g, '')
        .replace(/\[(.*?)\]\([^\)]+\)/g, '$1')
        .replace(/\s+/g, ' ')
        .trim()
        .slice(0, 160);
}

function showWhatsAppToast(title, bodyText) {
    if (!waToastBanner) return;
    if (waToastTitle) waToastTitle.innerText = title;
    if (waToastText) waToastText.innerText = bodyText;
    waToastBanner.classList.remove('hidden');
    if (waToastTimer) clearTimeout(waToastTimer);
    waToastTimer = setTimeout(() => {
        waToastBanner.classList.add('hidden');
    }, 5500);
}

if (waToastBanner) {
    waToastBanner.addEventListener('click', () => {
        waToastBanner.classList.add('hidden');
        chatContainer.scrollTop = chatContainer.scrollHeight;
    });
}

async function triggerPhoneNotification(rawContent, customTitle = null, stepIndex = null) {
    const chatName = (currentChatTitle && currentChatTitle.innerText) ? currentChatTitle.innerText : 'Antigravity';
    const title = customTitle || `🤖 TARS (${activePcName}) • ${chatName}`;
    const body = cleanPreviewText(rawContent);

    updateMediaSessionNotification(body);
    if (!isMobileVoiceMuted) {
        try {
            const chime = new Audio('/static/wa_notify.wav');
            chime.volume = 0.85;
            chime.play().catch(() => {});
        } catch (e) {}
    }

    if (navigator.vibrate) {
        navigator.vibrate([300, 120, 300, 120, 400]);
    }
    showWhatsAppToast(title, body);

    if (isPushSubscribed) {
        return;
    }

    if ('Notification' in window && Notification.permission === 'granted') {
        const notifTag = stepIndex ? `tars-step-${stepIndex}` : 'tars-msg-latest';
        const options = {
            body: body,
            icon: '/static/icon-192.png',
            badge: '/static/icon-192.png',
            vibrate: [300, 120, 300, 120, 400],
            requireInteraction: true,
            tag: notifTag,
            renotify: false,
            actions: [
                {
                    action: 'toggle_voice',
                    title: isMobileVoiceMuted ? '🔊 Activar voz' : '🔇 Silenciar voz'
                },
                {
                    action: 'open',
                    title: '📱 Abrir TARS'
                }
            ]
        };
        try {
            if (swRegistration && swRegistration.showNotification) {
                const existing = await swRegistration.getNotifications({ tag: notifTag });
                if (!existing || existing.length === 0) {
                    await swRegistration.showNotification(title, options);
                }
                return;
            }
        } catch (e) {}
        try {
            new Notification(title, options);
        } catch (e) {}
    }
}

async function acquireWakeLock(enable) {
    if (!('wakeLock' in navigator)) return;
    try {
        if (enable && !wakeLockSentinel) {
            wakeLockSentinel = await navigator.wakeLock.request('screen');
        } else if (!enable && wakeLockSentinel) {
            await wakeLockSentinel.release();
            wakeLockSentinel = null;
        }
    } catch (e) {}
}

async function activateNotificationsAndTest() {
    unlockMobileAudio();
    if (navigator.vibrate) navigator.vibrate([300, 120, 300, 120, 400]);

    if ('Notification' in window && Notification.permission !== 'granted') {
        try {
            await Notification.requestPermission();
        } catch (e) {}
    }

    const pushOk = await setupWebPushSubscription();
    if (!pushOk && !window.location.hostname.endsWith('.trycloudflare.com')) {
        try {
            const r = await fetch('/api/tunnel_url');
            const d = await r.json();
            if (d.tunnel_url) {
                window.location.href = d.tunnel_url;
                return;
            }
        } catch (e) {}
    }

    updateNotifyBtnUI(pushOk);
    showWhatsAppToast(
        '🤖 TARS • Prueba en 5 seg',
        'Salí de Chrome a la pantalla principal ahora: en 5 segundos te vibra y llega la notificación arriba.'
    );
    try {
        await fetch('/api/test_notify', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ delay: 5 })
        });
    } catch (e) {}
}

if (notifyToggleBtn) {
    notifyToggleBtn.addEventListener('click', activateNotificationsAndTest);
}

if (waToastBanner) {
    waToastBanner.addEventListener('click', () => {
        if ('Notification' in window && Notification.permission !== 'granted') {
            activateNotificationsAndTest();
        }
    });
}

if ('Notification' in window && Notification.permission !== 'granted') {
    setTimeout(() => {
        showWhatsAppToast(
            '🔔 TOCA ACÁ PARA ACTIVAR ALERTAS',
            'Toca este cartel verde para habilitar las notificaciones y vibración de Android.'
        );
    }, 800);
}

document.addEventListener('click', () => {
    if ('Notification' in window && Notification.permission === 'default') {
        Notification.requestPermission().then(() => {
            updateNotifyBtnUI();
            setupWebPushSubscription();
        }).catch(() => {});
    }
}, { once: true });

// Sincronizacion en tiempo real con la sesion activa de Antigravity (con lock anti-duplicados)
let currentSyncIndex = 0;
let isSyncing = false;
let lastProgressToastTs = 0;
let lastProgressToastStep = 0;
const renderedStepIndices = new Set();

async function syncWithAntigravity() {
    if (isSyncing) return;
    isSyncing = true;
    try {
        const resp = await fetch(`/api/sync?last_index=${currentSyncIndex}&chat_id=${encodeURIComponent(activeChatId)}`);
        const data = await resp.json();

        if (data.active_pc) {
            updateActivePcUI(data.active_pc);
        }

        if (data.chat_id) {
            activeChatId = data.chat_id;
        }
        if (data.current_model) {
            updateCurrentModelUI(data.current_model);
        }

        if (typeof data.pc_audio_muted === 'boolean' && data.pc_audio_muted !== isPcSoundMuted) {
            updatePcSoundUI(data.pc_audio_muted);
        }

        if (typeof data.mobile_voice_muted === 'boolean' && data.mobile_voice_muted !== isMobileVoiceMuted) {
            updateMobileVoiceUI(data.mobile_voice_muted);
        }

        if (data.processing_info && data.processing_info.is_processing) {
            updateProcessingBubble(data.processing_info);
            const actDesc = data.processing_info.tool_action || "Pensando...";
            const stepsCnt = data.processing_info.steps_count || 1;
            micStatusLabel.innerText = `⏳ Paso ${stepsCnt}: ${actDesc}`;
            if (cancelProcBtn) cancelProcBtn.classList.add('active-danger');
            if (cancelProcLabel && !isRecording) cancelProcLabel.innerText = 'Cortar IA';
            acquireWakeLock(true);
        } else {
            removeProcessingBubble();
            acquireWakeLock(false);
            if (!isRecording && !activeFetchController) {
                if (cancelProcBtn) cancelProcBtn.classList.remove('active-danger');
                if (cancelProcLabel) cancelProcLabel.innerText = 'Cortar';
            }
            if (!isRecording && micStatusLabel.innerText.startsWith("⏳ ")) {
                micStatusLabel.innerText = 'Toca para hablar';
            }
        }

        if (data.chat_changed) {
            if (chatContainer) {
                chatContainer.innerHTML = `
                    <div class="chat-loading-placeholder">
                        <div class="loading-spinner"></div>
                        <span>Cambiando chats, por favor espere...</span>
                    </div>
                `;
            }
            if (micStatusLabel) {
                micStatusLabel.innerText = 'Cambiando chats, por favor espere...';
            }
            renderedStepIndices.clear();
            currentSyncIndex = data.step_index || 0;
            await loadInitialChatTitle();
            if (micStatusLabel) micStatusLabel.innerText = 'Toca para hablar';
        } else if (data.has_new && data.step_index > currentSyncIndex && !renderedStepIndices.has(data.step_index)) {
            removeProcessingBubble();
            clearUserCancelChips();
            if (cancelProcBtn && !isRecording) cancelProcBtn.classList.remove('active-danger');
            if (cancelProcLabel && !isRecording) cancelProcLabel.innerText = 'Cortar';
            const isFirstLoad = (currentSyncIndex === 0);
            currentSyncIndex = data.step_index;
            renderedStepIndices.add(data.step_index);
            appendMessage('assistant', data.content, data.media, data.audio_url, !isFirstLoad);
            if (!isFirstLoad && data.content) {
                triggerPhoneNotification(data.content, null, data.step_index);
            }
            micStatusLabel.innerText = 'Toca para hablar';
        } else if (data.step_index && currentSyncIndex === 0) {
            currentSyncIndex = data.step_index;
            renderedStepIndices.add(data.step_index);
        }
    } catch (e) {
        // Silencioso ante breves desconexiones
    } finally {
        isSyncing = false;
    }
}

loadInitialChatTitle();
setInterval(syncWithAntigravity, 1500);
syncWithAntigravity();

