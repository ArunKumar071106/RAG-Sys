/*
 * Arivazhai floating assistant for the college website.
 *
 *   <script src="https://<assistant-domain>/arivazhai-widget.js" defer></script>
 *
 * Adds the floating launcher (bottom-right) and the chat panel as a small transparent iframe of
 * this app (?widget=1). The iframe grows to fit the panel when it opens and shrinks back to the
 * launcher when it closes. Embedding is allowed by frame-ancestors in nginx.conf.
 */
(function () {
  "use strict";
  var script = document.currentScript;
  if (!script || window.__arivazhaiWidget) return;
  window.__arivazhaiWidget = true;
  var origin = new URL(script.src, location.href).origin;

  function start() {
    var frame = document.createElement("iframe");
    frame.src = origin + "/?widget=1&vw=" + window.innerWidth + "&vh=" + window.innerHeight;
    frame.title = "Arivazhai admission assistant";
    frame.setAttribute("allowtransparency", "true");
    var style = frame.style;
    style.position = "fixed";
    style.right = "0";
    style.bottom = "0";
    style.width = "150px";
    style.height = "160px";
    style.maxWidth = "100%";
    style.maxHeight = "100%";
    style.border = "0";
    style.background = "transparent";
    style.colorScheme = "normal";
    style.zIndex = "2147483000";
    document.body.appendChild(frame);

    function sendViewport() {
      if (frame.contentWindow) {
        frame.contentWindow.postMessage({ type: "arivazhai:viewport", width: window.innerWidth, height: window.innerHeight }, origin);
      }
    }

    window.addEventListener("resize", sendViewport);
    window.addEventListener("message", function (event) {
      if (event.origin !== origin || event.source !== frame.contentWindow) return;
      var data = event.data || {};
      if (data.type === "arivazhai:ready") sendViewport();
      if (data.type === "arivazhai:size" && typeof data.width === "string" && typeof data.height === "string") {
        style.width = data.width;
        style.height = data.height;
      }
    });
  }

  if (document.body) start();
  else document.addEventListener("DOMContentLoaded", start);
})();
