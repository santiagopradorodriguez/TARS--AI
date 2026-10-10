self.addEventListener('install', (event) => {
    self.skipWaiting();
});

self.addEventListener('activate', (event) => {
    event.waitUntil(self.clients.claim());
});

self.addEventListener('push', (event) => {
    let payload = {
        title: '🤖 TARS • Antigravity',
        body: 'Nuevo mensaje recibido',
        url: '/'
    };
    if (event.data) {
        try {
            payload = Object.assign(payload, event.data.json());
        } catch (e) {
            payload.body = event.data.text();
        }
    }
    const notifTag = payload.tag || 'tars-msg-latest';
    const options = {
        body: payload.body,
        icon: '/static/icon-192.png',
        badge: '/static/icon-192.png',
        vibrate: [300, 120, 300, 120, 400],
        requireInteraction: true,
        tag: notifTag,
        renotify: false,
        data: { url: payload.url || '/' }
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
    event.notification.close();
    const targetUrl = (event.notification.data && event.notification.data.url) || '/';
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
