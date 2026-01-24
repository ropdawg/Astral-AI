const CACHE_NAME = "astral-cache-v1";

self.addEventListener("install", event => {
  event.waitUntil(
    caches.open(CACHE_NAME).then(cache => {
      return cache.addAll([
        "/",
        "/index.html",

        /* CSS */
        "/styles/index.css",
        "/styles/response-style.css",

        /* JS */
        "/scripts/brain.js",
        "/scripts/apifree.min.js",

        /* ICONS (IMPORTANT) */
        "/img/icon-192.png",
        "/img/icon-512.png"
      ]);
    })
  );
});

self.addEventListener("fetch", event => {
  event.respondWith(
    caches.match(event.request).then(response => {
      return response || fetch(event.request);
    })
  );
});