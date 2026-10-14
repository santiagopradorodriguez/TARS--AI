// =========================================================================
// SISTEMA DE AUTENTICACION Y PIN DE SEGURIDAD
// =========================================================================
const _origFetch = window.fetch;
window.fetch = async function(...args) {
    let [resource, config] = args;
    config = config || {};
    config.headers = config.headers || {};
    const storedPin = localStorage.getItem('tars_pin');
    if (storedPin) {
        if (config.headers instanceof Headers) {
            config.headers.set('X-TARS-PIN', storedPin);
        } else if (Array.isArray(config.headers)) {
            config.headers.push(['X-TARS-PIN', storedPin]);
        } else {
            config.headers['X-TARS-PIN'] = storedPin;
        }
    }
    const response = await _origFetch(resource, config);
    if (response.status === 401) {
        try {
            const clone = response.clone();
            const d = await clone.json();
            if (d && d.auth_required) {
                showPinModal();
            }
        } catch(e) {}
    }
    return response;
};

let currentPinBuffer = '';
const pinModal = document.getElementById('pin-modal');
const pinCard = document.querySelector('.pin-card');
const pinDotsContainer = document.getElementById('pin-dots');
const pinErrorMsg = document.getElementById('pin-error-msg');

function showPinModal(errorText = '') {
    if (!pinModal) return;
    pinModal.classList.remove('hidden');
    currentPinBuffer = '';
    updatePinDots();
    if (errorText) {
        showPinError(errorText);
    } else if (pinErrorMsg) {
        pinErrorMsg.style.display = 'none';
        pinErrorMsg.innerText = '';
    }
}

function hidePinModal() {
    if (pinModal) {
        pinModal.classList.add('hidden');
    }
}

function updatePinDots() {
    if (!pinDotsContainer) return;
    const dots = pinDotsContainer.querySelectorAll('.pin-dot');
    dots.forEach((dot, idx) => {
        if (idx < currentPinBuffer.length) {
            dot.classList.add('filled');
        } else {
            dot.classList.remove('filled');
        }
    });
}

function showPinError(msg) {
    if (pinErrorMsg) {
        pinErrorMsg.innerText = msg;
        pinErrorMsg.style.display = 'block';
    }
    if (pinCard) {
        pinCard.classList.add('shake');
        setTimeout(() => pinCard.classList.remove('shake'), 450);
    }
}

async function submitPin() {
    if (currentPinBuffer.length < 4) return;
    try {
        const resp = await _origFetch('/api/verify_pin', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ pin: currentPinBuffer })
        });
        const data = await resp.json();
        if (data && data.success) {
            localStorage.setItem('tars_pin', currentPinBuffer);
            hidePinModal();
            if (typeof loadChatsList === 'function') loadChatsList();
            if (typeof syncWithAntigravity === 'function') syncWithAntigravity();
        } else {
            showPinError(data.error || 'PIN incorrecto');
            currentPinBuffer = '';
            updatePinDots();
        }
    } catch (err) {
        showPinError('Error de conexion al validar PIN');
        currentPinBuffer = '';
        updatePinDots();
    }
}

function handlePinKey(val) {
    if (val === 'clear') {
        currentPinBuffer = '';
        if (pinErrorMsg) pinErrorMsg.style.display = 'none';
        updatePinDots();
        return;
    }
    if (val === 'backspace') {
        currentPinBuffer = currentPinBuffer.slice(0, -1);
        if (pinErrorMsg) pinErrorMsg.style.display = 'none';
        updatePinDots();
        return;
    }
    if (/^[0-9]$/.test(val) && currentPinBuffer.length < 6) {
        currentPinBuffer += val;
        if (pinErrorMsg) pinErrorMsg.style.display = 'none';
        updatePinDots();
        if (currentPinBuffer.length === 4) {
            submitPin();
        }
    }
}

document.querySelectorAll('.pin-key').forEach(keyBtn => {
    keyBtn.addEventListener('click', () => {
        const val = keyBtn.getAttribute('data-val') || keyBtn.getAttribute('data-action');
        handlePinKey(val);
    });
});

window.addEventListener('keydown', (e) => {
    if (!pinModal || pinModal.classList.contains('hidden')) return;
    if (/^[0-9]$/.test(e.key)) {
        handlePinKey(e.key);
    } else if (e.key === 'Backspace') {
        handlePinKey('backspace');
    } else if (e.key === 'Escape') {
        handlePinKey('clear');
    }
});

_origFetch('/api/auth_status', {
    headers: { 'X-TARS-PIN': localStorage.getItem('tars_pin') || '' }
})
.then(r => r.json())
.then(data => {
    if (data && !data.authenticated) {
        showPinModal();
    }
})
.catch(() => {});

// =========================================================================
// 1. NUCLEO CENTRAL REACTIVO (CANVAS OSCILOSCOPIO & ESTADOS DEL AGENTE)
// =========================================================================
const coreCanvas = document.getElementById('tars-core-canvas');
const coreStateReadout = document.getElementById('core-state-readout');
const hudStatusDot = document.getElementById('hud-status-dot');
let coreState = 'IDLE'; // 'IDLE' | 'LISTENING' | 'PROCESSING' | 'SPEAKING'
let corePhase = 0;

function setCoreState(nextState) {
    coreState = nextState;
    if (coreStateReadout) {
        const labels = {
            IDLE: 'STATE // STANDBY',
            LISTENING: 'STATE // MIC CAPTURE',
            PROCESSING: 'STATE // LINUX EXEC',
            SPEAKING: 'STATE // VOICE SYNTH'
        };
        coreStateReadout.innerText = labels[nextState] || 'STATE // STANDBY';
    }
    if (hudStatusDot) {
        hudStatusDot.className = 'status-indicator';
        if (nextState === 'LISTENING') hudStatusDot.classList.add('alert');
        else if (nextState === 'PROCESSING') hudStatusDot.classList.add('busy');
        else hudStatusDot.classList.add('online');
    }
}

function renderReactiveCore() {
    if (!coreCanvas) return;
    if (document.visibilityState === 'hidden') {
        setTimeout(() => {
            requestAnimationFrame(renderReactiveCore);
        }, 250);
        return;
    }
    const dpr = window.devicePixelRatio || 1;
    const targetW = Math.round(220 * dpr);
    const targetH = Math.round(42 * dpr);
    if (coreCanvas.width !== targetW || coreCanvas.height !== targetH) {
        coreCanvas.width = targetW;
        coreCanvas.height = targetH;
    }

    const ctx = coreCanvas.getContext('2d');
    const w = coreCanvas.width;
    const h = coreCanvas.height;
    ctx.clearRect(0, 0, w, h);

    let strokeColor = '#00e5ff';
    let secondaryColor = 'rgba(0, 229, 255, 0.25)';
    let amp = 4.5 * dpr;
    let freq = 0.08 / dpr;
    let speed = 0.06;

    if (coreState === 'LISTENING') {
        strokeColor = '#ff3b30';
        secondaryColor = 'rgba(229, 169, 60, 0.45)';
        amp = 12.0 * dpr;
        freq = 0.22 / dpr;
        speed = 0.22;
    } else if (coreState === 'PROCESSING') {
        strokeColor = '#e5a93c';
        secondaryColor = 'rgba(0, 229, 255, 0.35)';
        amp = 8.5 * dpr;
        freq = 0.16 / dpr;
        speed = 0.18;
    } else if (coreState === 'SPEAKING') {
        strokeColor = '#00e5ff';
        secondaryColor = 'rgba(0, 229, 255, 0.45)';
        amp = 10.5 * dpr;
        freq = 0.18 / dpr;
        speed = 0.16;
    }

    corePhase += speed;

    // Reticula central tenue
    ctx.strokeStyle = 'rgba(255, 255, 255, 0.07)';
    ctx.lineWidth = 1 * dpr;
    ctx.beginPath();
    ctx.moveTo(0, h / 2);
    ctx.lineTo(w, h / 2);
    ctx.stroke();

    // Onda armonica secundaria
    ctx.strokeStyle = secondaryColor;
    ctx.lineWidth = 1 * dpr;
    ctx.beginPath();
    for (let x = 0; x < w; x++) {
        const envelope = Math.sin((x / w) * Math.PI);
        const y = (h / 2) + Math.cos(x * freq * 1.4 - corePhase * 1.3) * (amp * 0.75) * envelope;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();

    // Onda tactica primaria
    ctx.strokeStyle = strokeColor;
    ctx.lineWidth = 1.5 * dpr;
    ctx.beginPath();
    for (let x = 0; x < w; x++) {
        const envelope = Math.sin((x / w) * Math.PI);
        const mod = (coreState === 'PROCESSING') ? Math.sin(x * 0.4 + corePhase) : 1;
        const y = (h / 2) + Math.sin(x * freq + corePhase) * amp * envelope * mod;
        if (x === 0) ctx.moveTo(x, y);
        else ctx.lineTo(x, y);
    }
    ctx.stroke();

    requestAnimationFrame(renderReactiveCore);
}
if (coreCanvas) {
    requestAnimationFrame(renderReactiveCore);
}

// =========================================================================
// 2. NAVEGACION POR MODULOS (DOCK TACTICO INFERIOR)
// =========================================================================
const dockTabs = document.querySelectorAll('.dock-tab');
const moduleViews = document.querySelectorAll('.hud-module-view');

if (dockTabs.length > 0) {
    dockTabs.forEach(tab => {
        tab.addEventListener('click', () => {
            const targetId = tab.getAttribute('data-target');
            dockTabs.forEach(t => t.classList.remove('active'));
            moduleViews.forEach(v => v.classList.remove('active'));
            tab.classList.add('active');
            const targetEl = document.getElementById(targetId);
            if (targetEl) targetEl.classList.add('active');
            if (targetId === 'view-telemetry' && typeof loadTelemetryPcs === 'function') {
                loadTelemetryPcs();
            }
        });
    });
}

// =========================================================================
// 3. BURBUJA DE PENSAMIENTO EN VIVO Y RENDERIZADO MARKDOWN + KATEX
// =========================================================================
const SVG_ICON_WAIT = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="#e5a93c" stroke-width="2"><circle cx="12" cy="12" r="9"/><polyline points="12 7 12 12 15 15"/></svg>`;
const SVG_ICON_DONE = `<svg viewBox="0 0 24 24" width="12" height="12" fill="none" stroke="#00e5ff" stroke-width="2"><polyline points="20 6 9 17 4 12"/></svg>`;

function updateProcessingBubble(info) {
    setCoreState('PROCESSING');
    if (!chatContainer) return;
    let bubble = document.getElementById('processing-bubble');
    if (!bubble) {
        bubble = document.createElement('div');
        bubble.id = 'processing-bubble';
        bubble.className = 'message assistant processing-card';
        chatContainer.appendChild(bubble);
    }

    const stepsCount = info.steps_count || 1;
    const actionText = escapeHtml(info.tool_action || info.thought || 'Ejecutando operacion...');
    const detailHtml = info.tool_detail ? `<div class="proc-detail">${escapeHtml(info.tool_detail)}</div>` : '';

    let stepsListHtml = '';
    if (Array.isArray(info.recent_steps) && info.recent_steps.length > 0) {
        const items = info.recent_steps.map((st, idx) => {
            const isLast = (idx === info.recent_steps.length - 1);
            const iconSvg = isLast ? SVG_ICON_WAIT : SVG_ICON_DONE;
            return `<div class="proc-step-item ${isLast ? 'current' : 'done'}">${iconSvg} <span>${escapeHtml(st)}</span></div>`;
        }).join('');
        stepsListHtml = `<div class="processing-thought-box">${items}</div>`;
    } else {
        stepsListHtml = `<div class="processing-thought-box"><div class="proc-step-item current">${SVG_ICON_WAIT} <span>${actionText}</span></div></div>`;
    }

    bubble.innerHTML = `
        <div class="processing-card-header">
            <div class="processing-header-left">
                <span class="processing-pulse"></span>
                <span class="processing-title">PROCESANDO EN NODO // PASO ${stepsCount}</span>
            </div>
            <button class="proc-stop-inline-btn" onclick="window.cancelCurrentProcessing()" title="Cortar procesamiento de inmediato">
                <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor"><rect x="5" y="5" width="14" height="14"/></svg>
                ABORTAR
            </button>
        </div>
        ${stepsListHtml}
        <div class="processing-tool-box">
            <span class="proc-badge">ACTIVO</span>
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
    if (!isRecording && !currentAudio) {
        setCoreState('IDLE');
    }
}

function escapeHtml(str) {
    return String(str)
        .replace(/&/g, '&amp;')
        .replace(/</g, '&lt;')
        .replace(/>/g, '&gt;')
        .replace(/"/g, '&quot;')
        .replace(/'/g, '&#039;');
}

window.copyCode = function(btn) {
    if (!btn) return;
    const wrapper = btn.closest('.code-block-wrapper');
    if (!wrapper) return;
    const codeEl = wrapper.querySelector('code');
    if (!codeEl) return;
    const code = codeEl.innerText;
    navigator.clipboard.writeText(code).then(() => {
        const oldText = btn.innerText;
        btn.innerText = 'COPIADO';
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
        const langLabel = lang ? '<span class="code-lang">' + escapeHtml(lang).toUpperCase() + '</span>' : '<span class="code-lang">CODE</span>';
        codeBlocks.push(
            '<div class="code-block-wrapper">' +
                '<div class="code-header">' +
                    langLabel +
                    '<button class="copy-code-btn" onclick="window.copyCode(this)">COPIAR</button>' +
                '</div>' +
                '<pre><code>' + escapedCode + '</code></pre>' +
            '</div>'
        );
        return id;
    });

    // 1.b Extraer bloques matematicos LaTeX ($$...$$ y $...$) para renderizar con KaTeX
    const mathBlocks = [];
    processed = processed.replace(/\$\$([\s\S]+?)\$\$/g, (m, tex) => {
        const id = '___MATHBLOCK_' + mathBlocks.length + '___';
        if (window.katex) {
            try {
                mathBlocks.push(window.katex.renderToString(tex.trim(), { displayMode: true, throwOnError: false }));
            } catch (e) {
                mathBlocks.push(`<code>${escapeHtml(tex)}</code>`);
            }
        } else {
            mathBlocks.push(`<code>$$${escapeHtml(tex)}$$</code>`);
        }
        return id;
    });

    processed = processed.replace(/\$([^\$\n]+?)\$/g, (m, tex) => {
        const id = '___MATHBLOCK_' + mathBlocks.length + '___';
        if (window.katex) {
            try {
                mathBlocks.push(window.katex.renderToString(tex.trim(), { displayMode: false, throwOnError: false }));
            } catch (e) {
                mathBlocks.push(`<code>${escapeHtml(tex)}</code>`);
            }
        } else {
            mathBlocks.push(`<code>$${escapeHtml(tex)}$</code>`);
        }
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

    // 9. Links markdown [texto](url), [texto](file://...) y URLs sueltas
    processed = processed.replace(/\[(.*?)\]\((https?:\/\/[^\)]+)\)/g, '<a href="$2" target="_blank" rel="noopener">$1</a>');
    processed = processed.replace(/\[(.*?)\]\(file:\/\/(\/[^\)\s#]+)(?:#[^\)\s]*)?\)/g, (m, label, fpath) => {
        return `<a href="/api/download?path=${encodeURIComponent(fpath)}" download class="inline-file-link" title="Descargar archivo">${label} [DL]</a>`;
    });
    processed = processed.replace(/(^|[^"'>])(https?:\/\/[^\s<]+)/g, '$1<a href="$2" target="_blank" rel="noopener">$2</a>');

    // 10. Parrafos y saltos de linea
    processed = processed.replace(/\n{2,}/g, '</p><p>');
    processed = processed.replace(/\n/g, '<br>');
    processed = '<p>' + processed + '</p>';

    // Limpieza
    processed = processed.replace(/<p><\/p>/g, '');
    processed = processed.replace(/<p>(<h[2-4]>.*?<\/h[2-4]>)<\/p>/g, '$1');
    processed = processed.replace(/<p>(<div class="code-block-wrapper">[\s\S]*?<\/div>)<\/p>/g, '$1');
    processed = processed.replace(/<p>(<blockquote>[\s\S]*?<\/blockquote>)<\/p>/g, '$1');

    // 11. Restaurar bloques matematicos y de codigo
    mathBlocks.forEach((block, idx) => {
        processed = processed.replace('___MATHBLOCK_' + idx + '___', block);
    });
    codeBlocks.forEach((block, idx) => {
        processed = processed.replace('___CODEBLOCK_' + idx + '___', block);
    });

    return processed;
}

// =========================================================================
// 4. AUDIO KEEP-ALIVE, SINTESIS DE VOZ Y CONTROLES DE REPRODUCCION
// =========================================================================
let audioUnlocked = false;
let bgKeepAliveAudio = null;

function updateMediaSessionNotification(textPreview) {
    if ('mediaSession' in navigator) {
        try {
            const chatName = (currentChatTitle && currentChatTitle.innerText)
                ? currentChatTitle.innerText
                : 'Antigravity';
            navigator.mediaSession.metadata = new MediaMetadata({
                title: textPreview || 'TARS Enlace Activo',
                artist: `TARS // ${chatName}`,
                album: 'TARS HUD Tactico',
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
        bgKeepAliveAudio = new Audio("data:audio/wav;base64,UklGRigAAABXQVZFZm10IBIAAAABAAEARKwAAIhYAQACABAAAABkYXRhAgAAAAEA");
        bgKeepAliveAudio.loop = true;
        bgKeepAliveAudio.volume = 0.01;
        bgKeepAliveAudio.play().then(() => {
            audioUnlocked = true;
            updateMediaSessionNotification('Sistemas en linea // Escuchando telemetria');
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
        const spanEl = currentAudioBtn.querySelector('span');
        if (spanEl) spanEl.innerText = 'REPRODUCIR VOZ';
        currentAudioBtn = null;
    }
    currentAudioUrl = null;
    if (audioControlBar) {
        audioControlBar.classList.add('hidden');
    }
    if (!isRecording) {
        setCoreState('IDLE');
    }
}

function pauseCurrentAudio() {
    if (currentAudio && !currentAudio.paused) {
        currentAudio.pause();
        setCoreState('IDLE');
        if (pauseIcon) pauseIcon.style.display = 'none';
        if (playIcon) playIcon.style.display = 'inline';
        if (audioStatusText) audioStatusText.innerText = 'CANAL DE VOZ EN PAUSA';
        if (currentAudioBtn) {
            currentAudioBtn.classList.remove('playing');
            currentAudioBtn.classList.add('paused');
            const spanEl = currentAudioBtn.querySelector('span');
            if (spanEl) spanEl.innerText = 'REANUDAR VOZ';
        }
    }
}

function resumeCurrentAudio() {
    if (currentAudio && currentAudio.paused) {
        currentAudio.play().then(() => {
            setCoreState('SPEAKING');
            if (pauseIcon) pauseIcon.style.display = 'inline';
            if (playIcon) playIcon.style.display = 'none';
            if (audioStatusText) audioStatusText.innerText = 'SINTESIS VOCAL ACTIVA';
            if (currentAudioBtn) {
                currentAudioBtn.classList.remove('paused');
                currentAudioBtn.classList.add('playing');
                const spanEl = currentAudioBtn.querySelector('span');
                if (spanEl) spanEl.innerText = 'PAUSAR VOZ';
            }
        }).catch(() => {});
    }
}

function playAudioUrl(url, sourceBtn = null) {
    if (!url) return;
    if (currentAudio && currentAudioUrl === url) {
        if (currentAudio.paused) resumeCurrentAudio();
        else pauseCurrentAudio();
        return;
    }

    stopCurrentAudio();

    const audio = new Audio(url);
    currentAudio = audio;
    currentAudioUrl = url;
    currentAudioBtn = sourceBtn;

    audio.onended = () => stopCurrentAudio();
    audio.onerror = () => stopCurrentAudio();

    audio.play().then(() => {
        setCoreState('SPEAKING');
        if (audioControlBar) {
            audioControlBar.classList.remove('hidden');
            if (pauseIcon) pauseIcon.style.display = 'inline';
            if (playIcon) playIcon.style.display = 'none';
            if (audioStatusText) audioStatusText.innerText = 'SINTESIS VOCAL ACTIVA';
        }
        if (sourceBtn) {
            sourceBtn.classList.remove('paused');
            sourceBtn.classList.add('playing');
            const spanEl = sourceBtn.querySelector('span');
            if (spanEl) spanEl.innerText = 'PAUSAR VOZ';
        }
    }).catch(() => {
        stopCurrentAudio();
    });
}

if (audioPauseBtn) {
    audioPauseBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (currentAudio) {
            if (currentAudio.paused) resumeCurrentAudio();
            else pauseCurrentAudio();
        }
    });
}

if (audioStopBtn) {
    audioStopBtn.addEventListener('click', (e) => {
        e.preventDefault();
        stopCurrentAudio();
    });
}

// =========================================================================
// 5. MENSAJES, ADJUNTOS Y CAMARA TACTICA DIRECTA
// =========================================================================
function clearUserCancelChips() {
    document.querySelectorAll('.user-cancel-chip').forEach(btn => btn.remove());
}

function appendMessage(sender, text, media = null, audioUrl = null, autoPlay = true) {
    if (!chatContainer) return;
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
            <svg viewBox="0 0 24 24" width="11" height="11" fill="currentColor"><rect x="5" y="5" width="14" height="14"/></svg>
            <span>ABORTAR EJECUCION</span>
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
                    audioEl.style.height = '34px';
                    wrapper.appendChild(audioEl);
                }

                const a = document.createElement('a');
                a.href = item.url;
                a.className = 'file-card';
                a.download = fname;
                a.innerHTML = `
                    <div class="file-info">
                        <svg viewBox="0 0 24 24" width="16" height="16" fill="none" stroke="currentColor" stroke-width="2">
                            <path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/>
                            <polyline points="14 2 14 8 20 8"/>
                        </svg>
                        <span class="file-name">DESCARGAR // ${escapeHtml(fname)}</span>
                    </div>
                    <svg viewBox="0 0 24 24" width="15" height="15" fill="none" stroke="currentColor" stroke-width="2">
                        <path d="M21 15v4a2 2 0 01-2 2H5a2 2 0 01-2-2v-4"/>
                        <polyline points="7 10 12 15 17 10"/>
                        <line x1="12" y1="15" x2="12" y2="3"/>
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
            <svg viewBox="0 0 24 24" width="13" height="13" fill="none" stroke="currentColor" stroke-width="2">
                <polygon points="11 5 6 9 2 9 2 15 6 15 11 19 11 5"/>
                <path d="M15.54 8.46a5 5 0 010 7.07"/>
            </svg>
            <span>REPRODUCIR VOZ</span>
        `;
        audioBtn.onclick = () => playAudioUrl(audioUrl, audioBtn);
        contentDiv.appendChild(audioBtn);

        if (sender === 'assistant' && autoPlay && !isMobileVoiceMuted) {
            playAudioUrl(audioUrl, audioBtn);
        }
    }

    msgDiv.appendChild(contentDiv);
    chatContainer.appendChild(msgDiv);
    chatContainer.scrollTop = chatContainer.scrollHeight;
}

const attachBtn = document.getElementById('attach-btn');
const fileInput = document.getElementById('file-input');
const cameraBtn = document.getElementById('camera-btn');
const cameraInput = document.getElementById('camera-input');
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
            icon.innerHTML = `<svg viewBox="0 0 24 24" width="14" height="14" fill="none" stroke="currentColor" stroke-width="2"><path d="M14 2H6a2 2 0 00-2 2v16a2 2 0 002 2h12a2 2 0 002-2V8z"/></svg>`;
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
            for (const f of e.target.files) pendingAttachments.push(f);
            renderAttachmentPreviews();
            fileInput.value = '';
        }
    });
}

// Camara Tactica: captura directa y envio inmediato
if (cameraBtn && cameraInput) {
    cameraBtn.addEventListener('click', () => cameraInput.click());
    cameraInput.addEventListener('change', (e) => {
        if (e.target.files && e.target.files.length > 0) {
            for (const f of e.target.files) pendingAttachments.push(f);
            renderAttachmentPreviews();
            cameraInput.value = '';
            const currentPrompt = (textInput && textInput.value.trim()) || 'Analizar captura optica adjunta.';
            sendTextMessage(currentPrompt);
        }
    });
}

// =========================================================================
// 6. CANCELACION Y TRANSMISION A ENDPOINTS (/api/chat, /api/message, /api/audio)
// =========================================================================
const cancelProcBtn = document.getElementById('cancel-proc-btn');
const cancelProcLabel = document.getElementById('cancel-proc-label');
let recordingCancelled = false;
let activeFetchController = null;

window.cancelCurrentProcessing = async function() {
    if (navigator.vibrate) navigator.vibrate([80, 40, 80]);

    if (isRecording && mediaRecorder) {
        recordingCancelled = true;
        isRecording = false;
        if (micBtn) micBtn.classList.remove('recording');
        setCoreState('IDLE');
        if (cancelProcLabel) cancelProcLabel.innerText = 'ABORTAR';
        if (cancelProcBtn) cancelProcBtn.classList.remove('active-danger');
        if (micStatusLabel) micStatusLabel.innerText = 'TRANSMISION DE VOZ DESCARTADA';
        try { mediaRecorder.stop(); } catch (e) {}
        showWhatsAppToast('CAPTURA ANULADA', 'El paquete de audio fue descartado localmente.');
        return;
    }

    if (activeFetchController) {
        try { activeFetchController.abort(); } catch (e) {}
        activeFetchController = null;
    }

    stopCurrentAudio();
    removeProcessingBubble();
    clearUserCancelChips();
    setCoreState('IDLE');
    if (cancelProcBtn) cancelProcBtn.classList.remove('active-danger');
    if (cancelProcLabel) cancelProcLabel.innerText = 'ABORTAR';
    if (micStatusLabel) micStatusLabel.innerText = 'ENVIANDO INTERRUPCION A HOST...';

    try {
        const cancelResp = await fetch('/api/cancel', { method: 'POST' });
        if (!cancelResp.ok) {
            await fetch('/api/cancel_chat', { method: 'POST' }).catch(() => {});
        }
        if (micStatusLabel) micStatusLabel.innerText = 'EJECUCION INTERRUMPIDA';
        showWhatsAppToast('INTERRUPCION EJECUTADA', 'Se detuvo el procesamiento en Antigravity IDE.');
        setTimeout(() => {
            if (!isRecording && micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
        }, 2500);
    } catch (e) {
        await fetch('/api/cancel_chat', { method: 'POST' }).catch(() => {});
        if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
    }
};

if (cancelProcBtn) {
    cancelProcBtn.addEventListener('click', (e) => {
        e.preventDefault();
        window.cancelCurrentProcessing();
    });
}

async function sendTextMessage(text) {
    const trimmed = (text || '').trim();
    if (!trimmed && pendingAttachments.length === 0) return;

    const filesToSend = [...pendingAttachments];
    pendingAttachments = [];
    renderAttachmentPreviews();

    const userMedia = filesToSend.map(f => {
        if (f.type && f.type.startsWith('image/')) {
            return { type: 'image', url: URL.createObjectURL(f), name: f.name };
        }
        return { type: 'file', url: '#', name: f.name };
    });

    const userTextDisplay = trimmed || (filesToSend.length > 0 ? (filesToSend.length === 1 ? `[ADJUNTO: ${filesToSend[0].name}]` : `[${filesToSend.length} ADJUNTOS]`) : '');
    appendMessage('user', userTextDisplay, userMedia.length > 0 ? userMedia : null);
    if (textInput) textInput.value = '';

    setCoreState('PROCESSING');
    if (cancelProcBtn) cancelProcBtn.classList.add('active-danger');
    if (cancelProcLabel) cancelProcLabel.innerText = 'CORTAR IA';

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
            if (resp.status === 404) {
                resp = await fetch('/api/message', {
                    method: 'POST',
                    body: formData,
                    signal: activeFetchController.signal
                });
            }
        } else {
            const payload = JSON.stringify({ text: trimmed, chat_id: activeChatId || '' });
            resp = await fetch('/api/chat', {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: payload,
                signal: activeFetchController.signal
            });
            if (resp.status === 404) {
                resp = await fetch('/api/message', {
                    method: 'POST',
                    headers: { 'Content-Type': 'application/json' },
                    body: payload,
                    signal: activeFetchController.signal
                });
            }
        }
        activeFetchController = null;
        const data = await resp.json();
        if (data.sent_to_ide) {
            if (micStatusLabel) micStatusLabel.innerText = 'ANTIGRAVITY PROCESANDO EN NODO...';
        } else if (data.reply) {
            setCoreState('IDLE');
            appendMessage('assistant', data.reply, data.media, data.audio_url);
            if (cancelProcBtn) cancelProcBtn.classList.remove('active-danger');
        }
    } catch (err) {
        activeFetchController = null;
        setCoreState('IDLE');
        if (err && err.name === 'AbortError') return;
        appendMessage('assistant', 'ERROR DE ENLACE AL TRANSMITIR PAQUETE.');
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

    appendMessage('user', '[PAQUETE DE VOZ TRANSMITIDO]', userMedia.length > 0 ? userMedia : null);

    const formData = new FormData();
    formData.append('audio', blob, 'voice.webm');
    if (activeChatId) formData.append('chat_id', activeChatId);
    filesToSend.forEach(f => formData.append('files', f));

    setCoreState('PROCESSING');
    if (cancelProcBtn) cancelProcBtn.classList.add('active-danger');
    if (cancelProcLabel) cancelProcLabel.innerText = 'CORTAR IA';

    activeFetchController = new AbortController();
    try {
        if (micStatusLabel) micStatusLabel.innerText = 'TRANSCRIBIENDO SENAL DE VOZ...';
        const resp = await fetch('/api/audio', {
            method: 'POST',
            body: formData,
            signal: activeFetchController.signal
        });
        activeFetchController = null;
        const data = await resp.json();

        if (data.user_text) {
            const msgs = document.querySelectorAll('.message.user');
            if (msgs.length > 0) {
                const pEl = msgs[msgs.length - 1].querySelector('p');
                if (pEl) pEl.innerText = data.user_text;
            }
        }

        if (data.cancelled) {
            setCoreState('IDLE');
            if (micStatusLabel) micStatusLabel.innerText = 'TRANSMISION ANULADA';
            return;
        }

        if (data.sent_to_ide) {
            if (micStatusLabel) micStatusLabel.innerText = 'ANTIGRAVITY PROCESANDO EN NODO...';
        } else if (data.reply) {
            setCoreState('IDLE');
            appendMessage('assistant', data.reply, data.media, data.audio_url);
            if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
            if (cancelProcBtn) cancelProcBtn.classList.remove('active-danger');
        }
    } catch (err) {
        activeFetchController = null;
        setCoreState('IDLE');
        if (err && err.name === 'AbortError') return;
        appendMessage('assistant', 'ERROR PROCESANDO SENAL DE AUDIO EN HOST.');
        if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
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
            if (event.data.size > 0) audioChunks.push(event.data);
        };

        mediaRecorder.onstop = () => {
            stream.getTracks().forEach(track => track.stop());
            if (recordingCancelled) {
                audioChunks = [];
                recordingCancelled = false;
                return;
            }
            const audioBlob = new Blob(audioChunks, { type: 'audio/webm' });
            if (audioChunks.length > 0) sendAudioBlob(audioBlob);
        };

        mediaRecorder.start();
        isRecording = true;
        recordStartTime = Date.now();
        setCoreState('LISTENING');
        if (micBtn) micBtn.classList.add('recording');
        if (cancelProcBtn) cancelProcBtn.classList.add('active-danger');
        if (cancelProcLabel) cancelProcLabel.innerText = 'CANCELAR';
        if (micStatusLabel) micStatusLabel.innerText = 'CAPTURANDO AUDIO // TOCA MIC PARA ENVIAR';
    } catch (err) {
        alert('Acceso denegado al microfono. Verifica permisos HTTPS en el navegador.');
    }
}

function stopRecording() {
    if (!isRecording || !mediaRecorder) return;
    isRecording = false;
    if (micBtn) micBtn.classList.remove('recording');
    if (micStatusLabel) micStatusLabel.innerText = 'EMPAQUETANDO AUDIO...';
    mediaRecorder.stop();
}

if (micBtn) {
    micBtn.addEventListener('click', (e) => {
        e.preventDefault();
        if (!isRecording) startRecording();
        else stopRecording();
    });
}

if (sendBtn) {
    sendBtn.addEventListener('click', () => {
        if (textInput) sendTextMessage(textInput.value);
    });
}

if (textInput) {
    textInput.addEventListener('keydown', (e) => {
        if (e.key === 'Enter') sendTextMessage(textInput.value);
    });
}

// =========================================================================
// 7. CONTROL DE VOZ MOVIL, PWA Y MUTE DE PC (/api/toggle_pc_sound, /api/mute_pc)
// =========================================================================
const mobileVoiceToggleBtn = document.getElementById('mobile-voice-toggle-btn');
const mobileVoiceOnIcon = document.getElementById('mobile-voice-on-icon');
const mobileVoiceOffIcon = document.getElementById('mobile-voice-off-icon');
const mobileVoiceLabel = document.getElementById('mobile-voice-label');
let isMobileVoiceMuted = localStorage.getItem('tars_mobile_voice_muted') === 'true';

function updateMobileVoiceUI(muted) {
    isMobileVoiceMuted = !!muted;
    localStorage.setItem('tars_mobile_voice_muted', isMobileVoiceMuted ? 'true' : 'false');
    if (isMobileVoiceMuted) stopCurrentAudio();
    if (!mobileVoiceToggleBtn) return;
    if (isMobileVoiceMuted) {
        mobileVoiceToggleBtn.classList.add('muted');
        if (mobileVoiceOnIcon) mobileVoiceOnIcon.style.display = 'none';
        if (mobileVoiceOffIcon) mobileVoiceOffIcon.style.display = 'inline-block';
        if (mobileVoiceLabel) mobileVoiceLabel.innerText = 'MUDO';
    } else {
        mobileVoiceToggleBtn.classList.remove('muted');
        if (mobileVoiceOnIcon) mobileVoiceOnIcon.style.display = 'inline-block';
        if (mobileVoiceOffIcon) mobileVoiceOffIcon.style.display = 'none';
        if (mobileVoiceLabel) mobileVoiceLabel.innerText = 'VOZ';
    }
}
updateMobileVoiceUI(isMobileVoiceMuted);

if (mobileVoiceToggleBtn) {
    mobileVoiceToggleBtn.addEventListener('click', async () => {
        if (navigator.vibrate) navigator.vibrate(40);
        const nextMuted = !isMobileVoiceMuted;
        updateMobileVoiceUI(nextMuted);
        showWhatsAppToast(
            nextMuted ? 'SINTESIS VOCAL SILENCIADA' : 'SINTESIS VOCAL HABILITADA',
            nextMuted ? 'Modo silencioso activo en terminal movil.' : 'Reproduccion automatica de respuestas activa.'
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
        navigator.serviceWorker.register('/sw.js').catch(() => {});
    });
    navigator.serviceWorker.addEventListener('message', (event) => {
        if (event.data && event.data.type === 'SET_MOBILE_VOICE_MUTE') {
            updateMobileVoiceUI(Boolean(event.data.muted));
        }
    });
}

let deferredInstallPrompt = null;
const pwaInstallBtn = document.getElementById('pwa-install-btn');
const isRunningStandalone = window.matchMedia('(display-mode: standalone)').matches ||
                            window.navigator.standalone === true ||
                            document.referrer.includes('android-app://');

if (pwaInstallBtn && isRunningStandalone) {
    pwaInstallBtn.style.display = 'none';
}

window.addEventListener('beforeinstallprompt', (e) => {
    e.preventDefault();
    deferredInstallPrompt = e;
    if (pwaInstallBtn && !isRunningStandalone) pwaInstallBtn.style.display = 'inline-flex';
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
            } catch (err) {}
            deferredInstallPrompt = null;
        } else {
            alert('Para instalar TARS como App nativa: abre el menu del navegador y selecciona "Instalar aplicacion" o "Agregar a pantalla de inicio".');
        }
    });
}

const pcSoundToggleBtn = document.getElementById('pc-sound-toggle-btn');
const pcSoundOnIcon = document.getElementById('pc-sound-on-icon');
const pcSoundOffIcon = document.getElementById('pc-sound-off-icon');
const telemetryAudioVal = document.getElementById('telemetry-audio-val');
const telemetryMutePcBtn = document.getElementById('telemetry-mute-pc-btn');
let isPcSoundMuted = false;

function updatePcSoundUI(muted) {
    isPcSoundMuted = !!muted;
    if (telemetryAudioVal) {
        telemetryAudioVal.innerText = isPcSoundMuted ? 'SILENCIADO' : 'ACTIVO';
        telemetryAudioVal.style.color = isPcSoundMuted ? '#ff3b30' : '#00e5ff';
    }
    if (!pcSoundToggleBtn) return;
    if (isPcSoundMuted) {
        pcSoundToggleBtn.classList.add('muted');
        if (pcSoundOnIcon) pcSoundOnIcon.style.display = 'none';
        if (pcSoundOffIcon) pcSoundOffIcon.style.display = 'inline-block';
    } else {
        pcSoundToggleBtn.classList.remove('muted');
        if (pcSoundOnIcon) pcSoundOnIcon.style.display = 'inline-block';
        if (pcSoundOffIcon) pcSoundOffIcon.style.display = 'none';
    }
}

async function togglePcAudioMute() {
    try {
        let resp = await fetch('/api/toggle_pc_sound', { method: 'POST' });
        if (resp.status === 404) {
            resp = await fetch('/api/mute_pc', { method: 'POST' });
        }
        const data = await resp.json();
        if (data && data.success) {
            updatePcSoundUI(data.pc_audio_muted);
            showWhatsAppToast(
                data.pc_audio_muted ? 'AUDIO DE MAQUINA SILENCIADO' : 'AUDIO DE MAQUINA ACTIVO',
                `Estado de salida de audio actualizado en ${activePcName}.`
            );
        }
    } catch (e) {}
}

if (pcSoundToggleBtn) pcSoundToggleBtn.addEventListener('click', togglePcAudioMute);
if (telemetryMutePcBtn) telemetryMutePcBtn.addEventListener('click', togglePcAudioMute);

// =========================================================================
// 8. SELECTOR DE CHATS E HISTORIAL (/api/chats, /api/switch_chat, /api/chat_history)
// =========================================================================
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
    chatsList.innerHTML = '<div class="loading-chats">Sondeando sesiones abiertas...</div>';
    try {
        const resp = await fetch('/api/chats');
        const data = await resp.json();
        const chats = data.chats || [];
        activeChatId = data.current_id || '';

        if (chats.length === 0) {
            chatsList.innerHTML = `<div class="empty-chats">${escapeHtml(data.error || 'Sin sesiones activas')}</div>`;
            return;
        }

        chatsList.innerHTML = '';
        chats.forEach(chat => {
            const item = document.createElement('div');
            item.className = `chat-item ${chat.active ? 'active' : ''}`;
            const badgeHtml = chat.active ? '<span class="chat-item-badge">ACTIVO</span>' : '';
            item.innerHTML = `
                <span class="chat-item-title">${escapeHtml(chat.title)}</span>
                ${badgeHtml}
            `;
            if (chat.active && currentChatTitle) {
                currentChatTitle.innerText = chat.title;
            }
            item.addEventListener('click', () => switchAntigravityChat(chat.id));
            chatsList.appendChild(item);
        });
    } catch (err) {
        chatsList.innerHTML = '<div class="empty-chats">Error de enlace con el servidor</div>';
    }
}

function renderChatHistory(messages, lastStepIndex) {
    if (!chatContainer || !Array.isArray(messages)) return;
    chatContainer.innerHTML = '';
    renderedStepIndices.clear();

    if (messages.length === 0) {
        const title = currentChatTitle ? currentChatTitle.innerText : 'SESION';
        appendMessage('assistant', `SESION ACTIVA // ${title}. Listo para recibir comandos.`, null, null, false);
        currentSyncIndex = 0;
        return;
    }

    messages.forEach(msg => {
        const isAssistant = (msg.role === 'assistant');
        appendMessage(isAssistant ? 'assistant' : 'user', msg.content, msg.media || null, null, false);
        if (msg.step_index) renderedStepIndices.add(msg.step_index);
    });

    if (lastStepIndex) currentSyncIndex = lastStepIndex;
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
    } catch (e) {} finally {
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
            if (currentChatTitle) currentChatTitle.innerText = res.title;
            if (res.id) activeChatId = res.id;

            if (Array.isArray(res.messages) && res.messages.length > 0) {
                renderChatHistory(res.messages, res.last_step_index);
            } else {
                await loadChatHistory(activeChatId);
            }
            if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
            syncWithAntigravity();
        } else {
            alert(`Error al conmutar sesion: ${res.error || 'desconocido'}`);
            if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
        }
    } catch (err) {
        if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
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
        if (activeChatId) await loadChatHistory(activeChatId);
    } catch (e) {}
}

if (chatSelectorBtn) chatSelectorBtn.addEventListener('click', openChatsModal);
if (chatsModalClose) chatsModalClose.addEventListener('click', closeChatsModal);
if (chatsModalOverlay) chatsModalOverlay.addEventListener('click', closeChatsModal);
if (prevChatBtn) prevChatBtn.addEventListener('click', () => switchAntigravityChat('anterior'));
if (nextChatBtn) nextChatBtn.addEventListener('click', () => switchAntigravityChat('siguiente'));

// =========================================================================
// 9. SELECTOR DE MODELOS IA (/api/models, /api/switch_model)
// =========================================================================
const modelSelectorBtn = document.getElementById('model-selector-btn');
const currentModelTitle = document.getElementById('current-model-title');
const modelsModal = document.getElementById('models-modal');
const modelsModalOverlay = document.getElementById('models-modal-overlay');
const modelsModalClose = document.getElementById('models-modal-close');
const modelsList = document.getElementById('models-list');

function formatShortModelName(fullName) {
    if (!fullName) return 'MODELO IA';
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
    modelsList.innerHTML = '<div class="loading-chats">Consultando motores de inferencia...</div>';
    try {
        const resp = await fetch('/api/models');
        const data = await resp.json();
        const models = data.models || [];
        if (data.current_model) updateCurrentModelUI(data.current_model);
        if (models.length === 0) {
            modelsList.innerHTML = '<div class="empty-chats">Sin modelos reportados</div>';
            return;
        }
        modelsList.innerHTML = '';
        models.forEach(m => {
            const card = document.createElement('div');
            card.className = `model-item ${m.active ? 'active' : ''}`;

            const top = document.createElement('div');
            top.className = 'model-item-top';
            const statusBadge = m.active
                ? '<span class="chat-item-badge">ACTIVO</span>'
                : (m.effort ? `<span style="font-size:0.7rem;color:var(--text-muted);">${escapeHtml(m.effort)}</span>` : '');
            top.innerHTML = `<span class="model-item-name">${escapeHtml(m.name)}</span>${statusBadge}`;
            card.appendChild(top);

            if (m.has_effort) {
                const pills = document.createElement('div');
                pills.className = 'effort-pills';
                ['Low', 'Medium', 'High'].forEach(eff => {
                    const pill = document.createElement('button');
                    pill.className = `effort-pill ${(m.active && (data.current_model || '').toLowerCase().includes(eff.toLowerCase())) || (!m.active && m.effort === eff) ? 'active' : ''}`;
                    pill.innerText = eff.toUpperCase();
                    pill.addEventListener('click', (e) => {
                        e.stopPropagation();
                        switchAntigravityModel(m.name, eff);
                    });
                    pills.appendChild(pill);
                });
                card.appendChild(pills);
            }

            card.addEventListener('click', () => switchAntigravityModel(m.name, m.effort || null));
            modelsList.appendChild(card);
        });
    } catch (e) {
        modelsList.innerHTML = '<div class="empty-chats">Error consultando modelos</div>';
    }
}

async function switchAntigravityModel(modelName, effort = null) {
    closeModelsModal();
    if (micStatusLabel) micStatusLabel.innerText = `CONMUTANDO A ${modelName.toUpperCase()}...`;
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
            showWhatsAppToast('MOTOR IA ACTUALIZADO', `Inferencia activa: ${finalName}`);
            if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
        }
    } catch (e) {
        if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
    }
}

if (modelSelectorBtn) modelSelectorBtn.addEventListener('click', openModelsModal);
if (modelsModalClose) modelsModalClose.addEventListener('click', closeModelsModal);
if (modelsModalOverlay) modelsModalOverlay.addEventListener('click', closeModelsModal);

// =========================================================================
// 10. MODULO 2: DOMOTICA & LUCES TUYA (PORT 8080 CON FALLBACK A /api/tuya/*)
// =========================================================================
const tuyaEndpointInput = document.getElementById('tuya-endpoint-input');
const tuyaSaveHostBtn = document.getElementById('tuya-save-host-btn');
const tuyaConnBadge = document.getElementById('tuya-conn-badge');
const tuyaPowerOnBtn = document.getElementById('tuya-power-on-btn');
const tuyaPowerOffBtn = document.getElementById('tuya-power-off-btn');
const tuyaBrightnessSlider = document.getElementById('tuya-brightness-slider');
const tuyaBrightnessVal = document.getElementById('tuya-brightness-val');
const tuyaColorPicker = document.getElementById('tuya-color-picker');
const tuyaColorHex = document.getElementById('tuya-color-hex');
const tuyaApplyColorBtn = document.getElementById('tuya-apply-color-btn');
const tuyaTelemetryLog = document.getElementById('tuya-telemetry-log');

const defaultTuyaHost = `http://${window.location.hostname || '127.0.0.1'}:8080`;
let tuyaBaseUrl = localStorage.getItem('tars_tuya_base_url') || defaultTuyaHost;
if (tuyaEndpointInput) tuyaEndpointInput.value = tuyaBaseUrl;

function logTuyaEvent(msg) {
    if (!tuyaTelemetryLog) return;
    const ts = new Date().toLocaleTimeString('es-AR', { hour12: false });
    const line = document.createElement('div');
    line.innerText = `[${ts}] ${msg}`;
    tuyaTelemetryLog.prepend(line);
}

async function sendTuyaRequest(endpoint, payload) {
    const cleanBase = (tuyaBaseUrl || defaultTuyaHost).replace(/\/+$/, '');
    const targetUrl = `${cleanBase}${endpoint}`;
    const t0 = performance.now();
    try {
        const resp = await fetch(targetUrl, {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify(payload)
        });
        if (!resp.ok) throw new Error(`HTTP ${resp.status}`);
        const rtt = Math.round(performance.now() - t0);
        if (tuyaConnBadge) {
            tuyaConnBadge.innerText = `OK // ${rtt}ms`;
            tuyaConnBadge.classList.add('online');
        }
        logTuyaEvent(`POST ${endpoint} -> ${JSON.stringify(payload)} (${resp.status} en ${rtt}ms)`);
        if (navigator.vibrate) navigator.vibrate(25);
        return true;
    } catch (err) {
        // Fallback a proxy HTTPS en backend (/api/tuya/*) para evitar bloqueo de contenido mixto en movil
        try {
            const proxyEndpoint = `/api/tuya${endpoint}`;
            const respRel = await fetch(proxyEndpoint, {
                method: 'POST',
                headers: { 'Content-Type': 'application/json' },
                body: JSON.stringify(payload)
            });
            if (respRel.ok) {
                const rtt = Math.round(performance.now() - t0);
                if (tuyaConnBadge) {
                    tuyaConnBadge.innerText = `OK (PROXY) // ${rtt}ms`;
                    tuyaConnBadge.classList.add('online');
                }
                logTuyaEvent(`POST ${proxyEndpoint} -> ${JSON.stringify(payload)} [OK]`);
                if (navigator.vibrate) navigator.vibrate(25);
                return true;
            }
        } catch (e2) {}

        if (tuyaConnBadge) {
            tuyaConnBadge.innerText = 'ERR // OFFLINE';
            tuyaConnBadge.classList.remove('online');
        }
        logTuyaEvent(`ERROR POST ${targetUrl} -> Verifica servidor en puerto 8080 o proxy /api/tuya`);
        return false;
    }
}

if (tuyaSaveHostBtn && tuyaEndpointInput) {
    tuyaSaveHostBtn.addEventListener('click', () => {
        tuyaBaseUrl = tuyaEndpointInput.value.trim() || defaultTuyaHost;
        localStorage.setItem('tars_tuya_base_url', tuyaBaseUrl);
        logTuyaEvent(`Host domotico fijado en: ${tuyaBaseUrl}`);
    });
}

if (tuyaPowerOnBtn) {
    tuyaPowerOnBtn.addEventListener('click', () => sendTuyaRequest('/power', { state: true }));
}
if (tuyaPowerOffBtn) {
    tuyaPowerOffBtn.addEventListener('click', () => sendTuyaRequest('/power', { state: false }));
}

if (tuyaBrightnessSlider) {
    tuyaBrightnessSlider.addEventListener('input', () => {
        if (tuyaBrightnessVal) tuyaBrightnessVal.innerText = `${tuyaBrightnessSlider.value}%`;
    });
    tuyaBrightnessSlider.addEventListener('change', () => {
        const val = parseInt(tuyaBrightnessSlider.value, 10);
        sendTuyaRequest('/brightness', { brightness: val });
    });
}

if (tuyaColorPicker) {
    tuyaColorPicker.addEventListener('input', () => {
        if (tuyaColorHex) tuyaColorHex.innerText = tuyaColorPicker.value.toUpperCase();
    });
}

if (tuyaApplyColorBtn && tuyaColorPicker) {
    tuyaApplyColorBtn.addEventListener('click', () => {
        sendTuyaRequest('/color', { color: tuyaColorPicker.value });
    });
}

document.querySelectorAll('.swatch-btn').forEach(btn => {
    btn.addEventListener('click', () => {
        const hex = btn.getAttribute('data-hex');
        if (tuyaColorPicker) tuyaColorPicker.value = hex;
        if (tuyaColorHex) tuyaColorHex.innerText = hex.toUpperCase();
        sendTuyaRequest('/color', { color: hex });
    });
});

document.querySelectorAll('.tuya-preset-card').forEach(card => {
    card.addEventListener('click', async () => {
        document.querySelectorAll('.tuya-preset-card').forEach(c => c.classList.remove('active'));
        card.classList.add('active');
        const hex = card.getAttribute('data-color');
        const bright = parseInt(card.getAttribute('data-brightness'), 10);
        const name = card.getAttribute('data-name');

        if (tuyaColorPicker) tuyaColorPicker.value = hex;
        if (tuyaColorHex) tuyaColorHex.innerText = hex.toUpperCase();
        if (tuyaBrightnessSlider) tuyaBrightnessSlider.value = bright;
        if (tuyaBrightnessVal) tuyaBrightnessVal.innerText = `${bright}%`;

        logTuyaEvent(`Aplicando perfil ${name}...`);
        await sendTuyaRequest('/power', { state: true });
        await sendTuyaRequest('/color', { color: hex });
        await sendTuyaRequest('/brightness', { brightness: bright });
    });
});

// =========================================================================
// 11. MODULO 3: AGENDA, CUENTAS REGRESIVAS Y CRON JOBS
// =========================================================================
const timerLabelInput = document.getElementById('timer-label-input');
const timerMinutesInput = document.getElementById('timer-minutes-input');
const addTimerBtn = document.getElementById('add-timer-btn');
const sendAgentReminderBtn = document.getElementById('send-agent-reminder-btn');
const timersListContainer = document.getElementById('timers-list-container');
const activeTimersCount = document.getElementById('active-timers-count');

const cronExprInput = document.getElementById('cron-expr-input');
const cronCmdInput = document.getElementById('cron-cmd-input');
const addCronBtn = document.getElementById('add-cron-btn');
const syncCronBtn = document.getElementById('sync-cron-btn');
const cronListContainer = document.getElementById('cron-list-container');

let tacticalTimers = JSON.parse(localStorage.getItem('tars_tactical_timers') || '[]');
let tacticalCrons = JSON.parse(localStorage.getItem('tars_tactical_crons') || JSON.stringify([
    { id: 'c1', expr: '0 */4 * * *', cmd: 'backup_vault_obsidian.sh', status: 'ACTIVE' },
    { id: 'c2', expr: '30 8 * * 1-5', cmd: 'sync_ni_daq_logs.py --check', status: 'ACTIVE' }
]));

function saveTimers() {
    localStorage.setItem('tars_tactical_timers', JSON.stringify(tacticalTimers));
}

function saveCrons() {
    localStorage.setItem('tars_tactical_crons', JSON.stringify(tacticalCrons));
}

function formatRemainingTime(ms) {
    if (ms <= 0) return '00:00:00';
    const totalSecs = Math.floor(ms / 1000);
    const hrs = String(Math.floor(totalSecs / 3600)).padStart(2, '0');
    const mins = String(Math.floor((totalSecs % 3600) / 60)).padStart(2, '0');
    const secs = String(totalSecs % 60).padStart(2, '0');
    return `${hrs}:${mins}:${secs}`;
}

function renderTimers() {
    if (!timersListContainer) return;
    const now = Date.now();
    if (activeTimersCount) {
        activeTimersCount.innerText = `${tacticalTimers.length} ACTIVOS`;
    }
    if (tacticalTimers.length === 0) {
        timersListContainer.innerHTML = '<div class="empty-chats">Sin cuentas regresivas activas</div>';
        return;
    }

    timersListContainer.innerHTML = '';
    tacticalTimers.forEach((t, idx) => {
        const rem = t.targetTs - now;
        if (rem <= 0 && !t.fired) {
            t.fired = true;
            saveTimers();
            triggerPhoneNotification(`Temporizador completado: ${t.label}`, 'ALERTA DE TEMPORIZADOR // TARS');
        }
        const item = document.createElement('div');
        item.className = 'hud-list-item';
        item.innerHTML = `
            <div class="hud-list-item-info">
                <span class="hud-list-item-title">${escapeHtml(t.label)}</span>
                <span class="hud-list-item-sub">${t.fired ? 'EXPIRADO' : 'EN CURSO'}</span>
            </div>
            <span class="timer-countdown-readout">${formatRemainingTime(rem)}</span>
            <button class="hud-btn-sm" data-rm-timer="${idx}">X</button>
        `;
        timersListContainer.appendChild(item);
    });

    timersListContainer.querySelectorAll('[data-rm-timer]').forEach(btn => {
        btn.addEventListener('click', () => {
            const i = parseInt(btn.getAttribute('data-rm-timer'), 10);
            tacticalTimers.splice(i, 1);
            saveTimers();
            renderTimers();
        });
    });
}

function renderCrons() {
    if (!cronListContainer) return;
    if (tacticalCrons.length === 0) {
        cronListContainer.innerHTML = '<div class="empty-chats">Sin tareas cron registradas</div>';
        return;
    }
    cronListContainer.innerHTML = '';
    tacticalCrons.forEach((c, idx) => {
        const item = document.createElement('div');
        item.className = 'hud-list-item';
        item.innerHTML = `
            <div class="hud-list-item-info">
                <span class="hud-list-item-title">${escapeHtml(c.cmd)}</span>
                <span class="hud-list-item-sub">CRON // ${escapeHtml(c.expr)}</span>
            </div>
            <span class="hud-badge">${escapeHtml(c.status || 'ACTIVE')}</span>
            <button class="hud-btn-sm" data-rm-cron="${idx}">X</button>
        `;
        cronListContainer.appendChild(item);
    });

    cronListContainer.querySelectorAll('[data-rm-cron]').forEach(btn => {
        btn.addEventListener('click', () => {
            const i = parseInt(btn.getAttribute('data-rm-cron'), 10);
            tacticalCrons.splice(i, 1);
            saveCrons();
            renderCrons();
        });
    });
}

if (addTimerBtn) {
    addTimerBtn.addEventListener('click', () => {
        const label = (timerLabelInput && timerLabelInput.value.trim()) || 'TEMPORIZADOR DE LABORATORIO';
        const mins = Math.max(1, parseInt(timerMinutesInput ? timerMinutesInput.value : '15', 10) || 15);
        tacticalTimers.push({
            label,
            targetTs: Date.now() + mins * 60 * 1000,
            fired: false
        });
        if (timerLabelInput) timerLabelInput.value = '';
        saveTimers();
        renderTimers();
    });
}

if (sendAgentReminderBtn) {
    sendAgentReminderBtn.addEventListener('click', () => {
        const label = (timerLabelInput && timerLabelInput.value.trim()) || 'Revision de proceso';
        const mins = Math.max(1, parseInt(timerMinutesInput ? timerMinutesInput.value : '15', 10) || 15);
        sendTextMessage(`Programa un recordatorio/alarma en ${mins} minutos para: ${label}`);
        const chatTab = document.querySelector('[data-target="view-chat"]');
        if (chatTab) chatTab.click();
    });
}

if (addCronBtn) {
    addCronBtn.addEventListener('click', () => {
        const expr = (cronExprInput && cronExprInput.value.trim()) || '0 * * * *';
        const cmd = (cronCmdInput && cronCmdInput.value.trim());
        if (!cmd) return;
        tacticalCrons.push({ id: String(Date.now()), expr, cmd, status: 'ACTIVE' });
        if (cronCmdInput) cronCmdInput.value = '';
        saveCrons();
        renderCrons();
    });
}

if (syncCronBtn) {
    syncCronBtn.addEventListener('click', () => {
        sendTextMessage('Lista mis cron jobs activos en Linux (crontab -l) y los timers de systemd activos.');
        const chatTab = document.querySelector('[data-target="view-chat"]');
        if (chatTab) chatTab.click();
    });
}

setInterval(renderTimers, 1000);
renderTimers();
renderCrons();

// =========================================================================
// 12. MODULO 4: TELEMETRIA & RED MULTI-PC (/api/pcs, /api/select_pc, /api/add_pc)
// =========================================================================
const pcSelectorBtn = document.getElementById('pc-selector-btn');
const currentPcTitle = document.getElementById('current-pc-title');
const pcsModal = document.getElementById('pcs-modal');
const pcsModalOverlay = document.getElementById('pcs-modal-overlay');
const pcsModalClose = document.getElementById('pcs-modal-close');
const pcsList = document.getElementById('pcs-list');
const customPcNameInput = document.getElementById('custom-pc-name');
const customPcIpInput = document.getElementById('custom-pc-ip');
const addCustomPcBtn = document.getElementById('add-custom-pc-btn');

const telemetryPcsList = document.getElementById('telemetry-pcs-list');
const telemetryRefreshPcsBtn = document.getElementById('telemetry-refresh-pcs-btn');
const telemetryPcNameInput = document.getElementById('telemetry-pc-name');
const telemetryPcIpInput = document.getElementById('telemetry-pc-ip');
const telemetryAddPcBtn = document.getElementById('telemetry-add-pc-btn');
const telemetryLatencyVal = document.getElementById('telemetry-latency-val');
const telemetryStepVal = document.getElementById('telemetry-step-val');
const telemetryNodeVal = document.getElementById('telemetry-node-val');
const telemetrySyncBadge = document.getElementById('telemetry-sync-badge');
const latencyBarsWrapper = document.getElementById('latency-bars-wrapper');

let activePcId = 'local';
let activePcName = 'PC';
const latencyHistory = [];

function recordLatencySample(rttMs) {
    latencyHistory.push(rttMs);
    if (latencyHistory.length > 24) latencyHistory.shift();
    if (telemetryLatencyVal) telemetryLatencyVal.innerText = `${rttMs} ms`;
    if (!latencyBarsWrapper) return;
    latencyBarsWrapper.innerHTML = '';
    const maxVal = Math.max(100, ...latencyHistory);
    latencyHistory.forEach(val => {
        const bar = document.createElement('div');
        bar.className = 'latency-bar';
        const pct = Math.max(10, Math.min(100, Math.round((val / maxVal) * 100)));
        bar.style.height = `${pct}%`;
        if (val > 250) bar.style.background = '#e5a93c';
        latencyBarsWrapper.appendChild(bar);
    });
}

function updateActivePcUI(pcInfo) {
    if (!pcInfo) return;
    activePcId = pcInfo.id || 'local';
    activePcName = pcInfo.name || 'PC';
    if (currentPcTitle) currentPcTitle.innerText = activePcName;
    if (telemetryNodeVal) telemetryNodeVal.innerText = activePcName.toUpperCase();
    if (pcSelectorBtn) {
        if (pcInfo.is_local) pcSelectorBtn.classList.remove('remote-active');
        else pcSelectorBtn.classList.add('remote-active');
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

function buildPcCardElement(pc) {
    const card = document.createElement('div');
    card.className = `pc-item ${pc.active ? 'active' : ''}`;
    const statusDotClass = pc.tars_online ? 'online' : (pc.online ? 'online' : 'offline');
    const statusLabel = pc.is_local
        ? 'POP!_OS LOCAL // ONLINE'
        : (pc.tars_online ? 'TAILSCALE // TARS ONLINE' : (pc.online ? 'TAILSCALE // ONLINE' : 'OFFLINE'));
    const activeBadge = pc.active ? '<span class="chat-item-badge">ACTIVA</span>' : '';
    const directLinkHtml = (!pc.is_local && pc.direct_url)
        ? `<a href="${escapeHtml(pc.direct_url)}" target="_blank" rel="noopener" class="pc-direct-link" onclick="event.stopPropagation()">DIRECTO</a>`
        : '';

    card.innerHTML = `
        <div class="pc-item-left">
            <div class="pc-item-title-row">
                <span class="pc-status-dot ${statusDotClass}"></span>
                <span class="pc-item-name">${escapeHtml(pc.name)}</span>
            </div>
            <div class="pc-item-sub">${escapeHtml(pc.ip)} // ${statusLabel}</div>
        </div>
        <div class="pc-item-right">
            ${directLinkHtml}
            ${activeBadge}
        </div>
    `;
    card.addEventListener('click', () => selectTargetPc(pc));
    return card;
}

async function loadPcsList() {
    if (!pcsList) return;
    pcsList.innerHTML = '<div class="loading-chats">Sondeando interfaces Tailscale...</div>';
    try {
        const resp = await fetch('/api/pcs');
        const data = await resp.json();
        if (data.active_pc) updateActivePcUI(data.active_pc);
        const pcs = data.pcs || [];
        if (pcs.length === 0) {
            pcsList.innerHTML = '<div class="empty-chats">Sin nodos detectados</div>';
            return;
        }
        pcsList.innerHTML = '';
        pcs.forEach(pc => pcsList.appendChild(buildPcCardElement(pc)));
    } catch (e) {
        pcsList.innerHTML = '<div class="empty-chats">Error consultando nodos</div>';
    }
}

async function loadTelemetryPcs() {
    if (!telemetryPcsList) return;
    telemetryPcsList.innerHTML = '<div class="loading-chats">Escaneando red Tailscale y LAN...</div>';
    try {
        const resp = await fetch('/api/pcs');
        const data = await resp.json();
        if (data.active_pc) updateActivePcUI(data.active_pc);
        const pcs = data.pcs || [];
        if (pcs.length === 0) {
            telemetryPcsList.innerHTML = '<div class="empty-chats">Sin nodos detectados</div>';
            return;
        }
        telemetryPcsList.innerHTML = '';
        pcs.forEach(pc => telemetryPcsList.appendChild(buildPcCardElement(pc)));
    } catch (e) {
        telemetryPcsList.innerHTML = '<div class="empty-chats">Error de telemetria de red</div>';
    }
}

async function selectTargetPc(pc) {
    closePcsModal();
    if (micStatusLabel) micStatusLabel.innerText = `ENLAZANDO CON ${pc.name.toUpperCase()}...`;
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
            loadTelemetryPcs();
            showWhatsAppToast(
                `NODO CONMUTADO // ${res.active_pc.name}`,
                `Enlace establecido con ${res.active_pc.ip}`
            );
            if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
        }
    } catch (e) {
        if (micStatusLabel) micStatusLabel.innerText = 'ERROR CONMUTANDO NODO';
    }
}

async function submitNewPc(ipVal, nameVal) {
    if (!ipVal) return;
    try {
        const resp = await fetch('/api/add_pc', {
            method: 'POST',
            headers: { 'Content-Type': 'application/json' },
            body: JSON.stringify({ ip: ipVal, name: nameVal })
        });
        const data = await resp.json();
        if (data && data.success) {
            if (data.active_pc) {
                updateActivePcUI(data.active_pc);
                renderedStepIndices.clear();
                currentSyncIndex = 0;
                activeChatId = '';
                loadInitialChatTitle();
                syncWithAntigravity();
            }
            closePcsModal();
            loadTelemetryPcs();
            showWhatsAppToast('NODO VINCULADO', `Direccion registrada: ${ipVal}`);
        }
    } catch (e) {}
}

if (pcSelectorBtn) pcSelectorBtn.addEventListener('click', openPcsModal);
if (pcsModalClose) pcsModalClose.addEventListener('click', closePcsModal);
if (pcsModalOverlay) pcsModalOverlay.addEventListener('click', closePcsModal);

if (addCustomPcBtn) {
    addCustomPcBtn.addEventListener('click', () => {
        submitNewPc(customPcIpInput ? customPcIpInput.value.trim() : '', customPcNameInput ? customPcNameInput.value.trim() : '');
        if (customPcIpInput) customPcIpInput.value = '';
        if (customPcNameInput) customPcNameInput.value = '';
    });
}

if (telemetryAddPcBtn) {
    telemetryAddPcBtn.addEventListener('click', () => {
        submitNewPc(telemetryPcIpInput ? telemetryPcIpInput.value.trim() : '', telemetryPcNameInput ? telemetryPcNameInput.value.trim() : '');
        if (telemetryPcIpInput) telemetryPcIpInput.value = '';
        if (telemetryPcNameInput) telemetryPcNameInput.value = '';
    });
}

if (telemetryRefreshPcsBtn) {
    telemetryRefreshPcsBtn.addEventListener('click', loadTelemetryPcs);
}

// =========================================================================
// 13. NOTIFICACIONES PUSH Y SINCRONIZACION EN TIEMPO REAL (/api/sync)
// =========================================================================
const notifyToggleBtn = document.getElementById('notify-toggle-btn');
const notifyBtnLabel = document.getElementById('notify-btn-label');
const waToastBanner = document.getElementById('wa-toast-banner');
const waToastTitle = document.getElementById('wa-toast-title');
const waToastText = document.getElementById('wa-toast-text');

let swRegistration = null;
let waToastTimer = null;
let wakeLockSentinel = null;
let isPushSubscribed = false;

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
        return false;
    }
}

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
    if (!raw) return 'Transmision recibida';
    return raw
        .replace(/```[\s\S]*?```/g, '[CODIGO] ')
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
        if (waToastBanner) waToastBanner.classList.add('hidden');
    }, 5000);
}

if (waToastBanner) {
    waToastBanner.addEventListener('click', () => {
        waToastBanner.classList.add('hidden');
        if (chatContainer) chatContainer.scrollTop = chatContainer.scrollHeight;
    });
}

async function triggerPhoneNotification(rawContent, customTitle = null, stepIndex = null) {
    const chatName = (currentChatTitle && currentChatTitle.innerText) ? currentChatTitle.innerText : 'Antigravity';
    const title = customTitle || `TARS (${activePcName}) // ${chatName}`;
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

    if (isPushSubscribed) return;

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
                { action: 'toggle_voice', title: isMobileVoiceMuted ? 'Activar voz' : 'Silenciar voz' },
                { action: 'open', title: 'Abrir TARS' }
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
        try { new Notification(title, options); } catch (e) {}
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
    if (navigator.vibrate) navigator.vibrate([250, 100, 250]);

    if ('Notification' in window && Notification.permission !== 'granted') {
        try { await Notification.requestPermission(); } catch (e) {}
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
    showWhatsAppToast('PRUEBA DE ALERTA EN 5s', 'Minimiza el navegador para verificar recepcion push.');
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

let currentSyncIndex = 0;
let isSyncing = false;
const renderedStepIndices = new Set();

async function syncWithAntigravity() {
    if (isSyncing) return;
    isSyncing = true;
    const t0 = performance.now();
    try {
        const resp = await fetch(`/api/sync?last_index=${currentSyncIndex}&chat_id=${encodeURIComponent(activeChatId)}`);
        const data = await resp.json();
        const rtt = Math.round(performance.now() - t0);
        recordLatencySample(rtt);

        if (telemetrySyncBadge) {
            telemetrySyncBadge.innerText = 'SYNC OK';
            telemetrySyncBadge.classList.add('online');
        }

        if (data.active_pc) updateActivePcUI(data.active_pc);
        if (data.chat_id) activeChatId = data.chat_id;
        if (data.current_model) updateCurrentModelUI(data.current_model);

        if (typeof data.pc_audio_muted === 'boolean' && data.pc_audio_muted !== isPcSoundMuted) {
            updatePcSoundUI(data.pc_audio_muted);
        }

        if (typeof data.mobile_voice_muted === 'boolean' && data.mobile_voice_muted !== isMobileVoiceMuted) {
            updateMobileVoiceUI(data.mobile_voice_muted);
        }

        if (data.processing_info && data.processing_info.is_processing) {
            updateProcessingBubble(data.processing_info);
            const actDesc = data.processing_info.tool_action || 'Ejecutando...';
            const stepsCnt = data.processing_info.steps_count || 1;
            if (micStatusLabel) micStatusLabel.innerText = `PASO ${stepsCnt} // ${actDesc.toUpperCase()}`;
            if (cancelProcBtn) cancelProcBtn.classList.add('active-danger');
            if (cancelProcLabel && !isRecording) cancelProcLabel.innerText = 'CORTAR IA';
            acquireWakeLock(true);
        } else {
            removeProcessingBubble();
            acquireWakeLock(false);
            if (!isRecording && !activeFetchController) {
                if (cancelProcBtn) cancelProcBtn.classList.remove('active-danger');
                if (cancelProcLabel) cancelProcLabel.innerText = 'ABORTAR';
            }
            if (!isRecording && micStatusLabel && micStatusLabel.innerText.startsWith('PASO ')) {
                micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
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
            if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
        } else if (data.has_new && data.step_index > currentSyncIndex && !renderedStepIndices.has(data.step_index)) {
            removeProcessingBubble();
            clearUserCancelChips();
            if (cancelProcBtn && !isRecording) cancelProcBtn.classList.remove('active-danger');
            if (cancelProcLabel && !isRecording) cancelProcLabel.innerText = 'ABORTAR';
            const isFirstLoad = (currentSyncIndex === 0);
            currentSyncIndex = data.step_index;
            renderedStepIndices.add(data.step_index);
            appendMessage('assistant', data.content, data.media, data.audio_url, !isFirstLoad);
            if (!isFirstLoad && data.content) {
                triggerPhoneNotification(data.content, null, data.step_index);
            }
            if (micStatusLabel) micStatusLabel.innerText = 'CANAL DE AUDIO EN ESPERA';
        } else if (data.step_index && currentSyncIndex === 0) {
            currentSyncIndex = data.step_index;
            renderedStepIndices.add(data.step_index);
        }

        if (telemetryStepVal) telemetryStepVal.innerText = String(currentSyncIndex);
    } catch (e) {
        if (telemetrySyncBadge) {
            telemetrySyncBadge.innerText = 'LINK LOSS';
            telemetrySyncBadge.classList.remove('online');
        }
    } finally {
        isSyncing = false;
    }
}

loadInitialChatTitle();
setInterval(syncWithAntigravity, 1500);
syncWithAntigravity();
