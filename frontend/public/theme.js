// Sets the theme before first paint. Mirrors initTheme in src/lib/theme.svelte.ts.
// A file rather than an inline script, so the Content-Security-Policy needs no 'unsafe-inline'.
(function () {
  var choice = "system";
  try {
    var stored = localStorage.getItem("gate-cache-theme");
    if (stored === "light" || stored === "dark") choice = stored;
  } catch (e) {}
  var dark = choice === "dark" || (choice === "system" && matchMedia("(prefers-color-scheme: dark)").matches);
  document.documentElement.dataset.theme = dark ? "dark" : "light";
})();
