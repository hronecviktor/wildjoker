// Wild Joker's service worker: makes the site installable as an app and
// starts it quickly.
//
// - Pages (/, invite links /j/ABCD) always come from the server, so a new
//   release shows up on the next launch; without a connection the offline
//   page explains why nothing works (the game needs the server anyway).
// - Built files under /assets/ have the content hash in their name and
//   never change, so they come from the cache once fetched.
// - Everything else (the game's WebSocket, /ice, /healthz) is left alone.
//
// A running game never switches versions: the page keeps the code it
// loaded, and only a new launch or reload picks up a new release.

const CACHE = "wildjoker-v1";
const SHELL = [
  "/offline.html",
  "/manifest.webmanifest",
  "/icons/icon-192.png",
  "/icons/icon-512.png",
  "/icons/favicon-32.png",
];

self.addEventListener("install", (event) => {
  event.waitUntil(
    caches
      .open(CACHE)
      .then((cache) => cache.addAll(SHELL))
      .then(() => self.skipWaiting()),
  );
});

self.addEventListener("activate", (event) => {
  event.waitUntil(
    caches
      .keys()
      .then((keys) => Promise.all(keys.filter((k) => k !== CACHE).map((k) => caches.delete(k))))
      .then(() => self.clients.claim()),
  );
});

self.addEventListener("fetch", (event) => {
  const request = event.request;
  if (request.method !== "GET") return;
  const url = new URL(request.url);
  if (url.origin !== self.location.origin) return;

  if (request.mode === "navigate") {
    event.respondWith(page(request));
  } else if (url.pathname.startsWith("/assets/")) {
    event.respondWith(cached(request));
  } else if (SHELL.includes(url.pathname) || url.pathname.startsWith("/icons/")) {
    event.respondWith(fresh(request));
  }
});

/** A page from the server, keeping the latest one; offline, the offline page. */
async function page(request) {
  try {
    const response = await fetch(request);
    if (response.ok && new URL(request.url).pathname === "/") void prune(response.clone());
    return response;
  } catch {
    return (await caches.match("/offline.html")) ?? Response.error();
  }
}

/** From the cache, or fetched and kept. */
async function cached(request) {
  const hit = await caches.match(request);
  if (hit) return hit;
  const response = await fetch(request);
  if (response.ok) {
    const cache = await caches.open(CACHE);
    await cache.put(request, response.clone());
  }
  return response;
}

/** From the server and kept, or the kept copy when offline. */
async function fresh(request) {
  try {
    const response = await fetch(request);
    if (response.ok) {
      const cache = await caches.open(CACHE);
      await cache.put(request, response.clone());
    }
    return response;
  } catch {
    return (await caches.match(request)) ?? Response.error();
  }
}

/** Forget built files the latest page no longer uses (from older releases). */
async function prune(response) {
  const html = await response.text();
  const cache = await caches.open(CACHE);
  for (const request of await cache.keys()) {
    const path = new URL(request.url).pathname;
    if (path.startsWith("/assets/") && !html.includes(path)) await cache.delete(request);
  }
}
