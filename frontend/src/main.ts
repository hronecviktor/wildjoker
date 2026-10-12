import { mount } from "svelte";
import App from "./App.svelte";
import "./app.css";
import "./lib/install.svelte";

// The service worker makes the site installable as an app (public/sw.js).
// Browsers only allow one on https pages and localhost.
if ("serviceWorker" in navigator && import.meta.env.PROD) {
  window.addEventListener("load", () => {
    navigator.serviceWorker.register("/sw.js").catch(() => {});
  });
}

export default mount(App, { target: document.getElementById("app")! });
