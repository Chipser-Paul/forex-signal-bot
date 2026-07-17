self.addEventListener("install", (event) => {
  event.waitUntil(
    caches.open("fsb-v1").then((cache) =>
      cache.addAll([
        "/",
        "/static/manifest.json",
        "/static/icon.svg"
      ])
    )
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  event.respondWith(
    fetch(request).catch(() => caches.match(request))
  );
});
