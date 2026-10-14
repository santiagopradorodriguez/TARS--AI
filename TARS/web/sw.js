self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('fetch', (event) => {
    // Requerido por los criterios de instalacion de PWA en Google Chrome
    if (event.request.method === 'GET') {
        event.respondWith(
            fetch(event.request).catch(() => caches.match(event.request))
        );
    }
});

self.addEventListener('push', (event) => {
    let payload = {
        title: '🤖 TARS • Antigravity',
        body: 'Nuevo mensaje recibido',
        url: '/',
        voice_muted: false
    };
    if (event.data) {
        try {
            payload = Object.assign(payload, event.data.json());
        } catch (e) {
            payload.body = event.data.text();
        }
    }
    const notifTag = payload.tag || 'tars-msg-latest';
    const isMuted = Boolean(payload.voice_muted);
    const options = {
        body: payload.body,
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        vibrate: [300, 120, 300, 120, 400],
        requireInteraction: true,
        tag: notifTag,
        renotify: false,
        actions: [
            {
                action: 'toggle_voice',
                title: isMuted ? '🔊 Activar voz' : '🔇 Silenciar voz'
            },
            {
                action: 'open',
                title: '📱 Abrir TARS'
            }
        ],
        data: {
            url: payload.url || '/',
            voice_muted: isMuted
        }
    };
    event.waitUntil(
        self.registration.getNotifications({ tag: notifTag }).then((existing) => {
            if (existing && existing.length > 0) {
                return;
            }
            return self.registration.showNotification(payload.title, options);
        })
    );
});

self.addEventListener('notificationclick', (event) => {
    const targetUrl = (event.notification.data && event.notification.data.url) || '/';

    if (event.action === 'toggle_voice') {
        event.notification.close();
        event.waitUntil(
            fetch('/api/toggle_mobile_voice', { method: 'POST' })
                .then((r) => r.json())
                .then((data) => {
                    const muted = Boolean(data && data.mobile_voice_muted);
                    return clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
                        for (const client of clientList) {
                            client.postMessage({
                                type: 'SET_MOBILE_VOICE_MUTE',
                                muted: muted
                            });
                        }
                        return self.registration.showNotification(
                            muted ? '🔇 Voz del celular desactivada' : '🔊 Voz del celular activada',
                            {
                                body: muted
                                    ? 'TARS no hablará en voz alta al llegar respuestas.'
                                    : 'TARS volverá a leer las respuestas por voz.',
                                icon: '/static/icon-192.png',
                                badge: '/static/icon-192.png',
                                tag: 'tars-voice-status',
                                silent: true
                            }
                        );
                    });
                })
                .catch(() => {})
        );
        return;
    }

    event.notification.close();
    event.waitUntil(
        clients.matchAll({ type: 'window', includeUncontrolled: true }).then((clientList) => {
            for (const client of clientList) {
                if ('focus' in client) {
                    return client.focus();
                }
            }
            if (clients.openWindow) {
                return clients.openWindow(targetUrl);
            }
        })
    );
});
