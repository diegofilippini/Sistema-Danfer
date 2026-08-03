const CACHE = "danfer-os-1.7.8";
const ASSETS = ["/", "/styles.css", "/styles-extra.css", "/app.js", "/manifest.json"];
self.addEventListener("install", event => {
  event.waitUntil(caches.open(CACHE).then(cache => cache.addAll(ASSETS)));
});
self.addEventListener("activate", event => {
  event.waitUntil(caches.keys().then(keys => Promise.all(
    keys.filter(key => key !== CACHE).map(key => caches.delete(key))
  )));
});
self.addEventListener("fetch", event => {
  if (event.request.method !== "GET" || event.request.url.includes("/api/")) return;
  event.respondWith(fetch(event.request).catch(() => caches.match(event.request)));
});
self.addEventListener("push", event => {
  let data = {title: "Danfer Industrial OS", body: "Há uma nova atualização.", url: "/"};
  try { data = {...data, ...event.data.json()}; } catch (_) {}
  event.waitUntil(self.registration.showNotification(data.title, {
    body: data.body,
    data: {url: data.url || "/"}, tag: "danfer-os-update",
  }));
});
self.addEventListener("notificationclick", event => {
  event.notification.close();
  event.waitUntil(clients.matchAll({type:"window", includeUncontrolled:true}).then(windows => {
    const existing = windows.find(window => "focus" in window);
    return existing ? existing.focus() : clients.openWindow(event.notification.data?.url || "/");
  }));
});
