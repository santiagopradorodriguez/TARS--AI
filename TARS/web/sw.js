const CACHE_NAME = 'tars-shell-v4.8';
const PRECACHE_ASSETS = [
    '/',
    '/static/style.css?v=4.8',
    '/static/app.js?v=4.8',
    '/static/connection_config.js',
    '/manifest.json',
    '/static/icon-192.png'
];

self.addEventListener('install', (event) => {
    event.waitUntil(
        caches.open(CACHE_NAME).then((cache) => {
            return cache.addAll(PRECACHE_ASSETS).catch((e) => {
                console.log('[SW] Precache parcial:', e);
            });
        }).then(() => self.skipWaiting())
    );
});

self.addEventListener('activate', (event) => {
    event.waitUntil(
        caches.keys().then((keys) => {
            return Promise.all(
                keys.filter((k) => k !== CACHE_NAME).map((k) => caches.delete(k))
            );
        }).then(() => self.clients.claim())
    );
});

self.addEventListener('fetch', (event) => {
    // No interceptar llamadas a APIs ni WebSockets para evitar romper la sincronizacion
    if (event.request.url.includes('/api/') || event.request.url.includes('/ws')) {
        return;
    }
    if (event.request.method === 'GET') {
        event.respondWith(
            fetch(event.request)
                .then((response) => {
                    if (response && response.status === 200) {
                        const copy = response.clone();
                        caches.open(CACHE_NAME).then((cache) => cache.put(event.request, copy));
                    }
                    return response;
                })
                .catch(async () => {
                    const cached = await caches.match(event.request);
                    if (cached) return cached;
                    const indexCached = await caches.match('/');
                    if (indexCached) return indexCached;
                    return new Response('Offline', { status: 503, statusText: 'Offline' });
                })
        );
    }
});

self.addEventListener('push', (event) => {
    let payload = {
        title: 'TARS - Antigravity',
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
                title: isMuted ? 'Activar voz' : 'Silenciar voz'
            },
            {
                action: 'open',
                title: 'Abrir TARS'
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
                            muted ? 'Voz del celular desactivada' : 'Voz del celular activada',
                            {
                                body: muted
                                    ? 'TARS no hablara en voz alta al llegar respuestas.'
                                    : 'TARS volvera a leer las respuestas por voz.',
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
