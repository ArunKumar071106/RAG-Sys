/*
 * Arivazhai settings - the only file to edit when hosting the page somewhere else.
 *
 * apiBaseUrl: where the backend runs.
 *   ""  (empty) when the backend serves this page itself (http://127.0.0.1:8000/) or a web server
 *       forwards /api to it (docker compose).
 *   "https://<hf-username>-arivazhai-api.hf.space" when the page is on another site (Netlify, the
 *       college website); that site's address must then be in the backend's CORS_ORIGINS.
 */
window.ARIVAZHAI_CONFIG = {
  apiBaseUrl: "",
  // how long to wait for an answer before saying it took too long
  chatTimeoutMs: 90000,
};
