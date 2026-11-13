/*
 * The page around the chat: the mobile menu and its sub-menus, the "Arivazhai" menu link, the
 * "Chat below" arrow, the robot's welcome, and starting the chat.
 */
(function (A) {
  "use strict";

  function setupMenu() {
    const toggle = document.querySelector(".menu-toggle");
    const nav = document.querySelector(".mainnav");
    if (toggle && nav) {
      const label = toggle.querySelector(".sr-only");
      const setOpen = (open) => {
        nav.classList.toggle("mainnav--open", open);
        toggle.setAttribute("aria-expanded", String(open));
        if (label) label.textContent = open ? "Close menu" : "Open menu";
      };
      toggle.addEventListener("click", () => setOpen(!nav.classList.contains("mainnav--open")));
      const arivazhai = nav.querySelector('a[href="#assistant"]');
      if (arivazhai) {
        arivazhai.addEventListener("click", (event) => {
          event.preventDefault();
          setOpen(false);
          A.chat.startChat();
        });
      }
    }

    // sub-menus open on click; a click elsewhere or Esc closes them
    document.querySelectorAll(".has-submenu").forEach((item) => {
      const button = item.querySelector(":scope > button");
      if (!button) return;
      const setOpen = (open) => {
        item.classList.toggle("is-open", open);
        button.setAttribute("aria-expanded", String(open));
      };
      button.addEventListener("click", () => setOpen(!item.classList.contains("is-open")));
      document.addEventListener("mousedown", (event) => {
        if (!item.contains(event.target)) setOpen(false);
      });
      document.addEventListener("keydown", (event) => {
        if (event.key === "Escape") setOpen(false);
      });
    });
  }

  /** The round down-arrow, shown while the question box is still below the screen. */
  function setupScrollToChat() {
    const button = document.querySelector(".scroll-to-chat");
    const target = document.querySelector(".chat__footer");
    if (!button) return;
    button.addEventListener("click", A.chat.startChat);
    if (!target || typeof IntersectionObserver === "undefined") return;
    new IntersectionObserver(([entry]) => {
      // hidden when the question box is on screen, or already scrolled past
      button.hidden = entry.isIntersecting || entry.boundingClientRect.top <= 0;
    }).observe(target);
  }

  /** On load the robot waves "Getting ready…" while the assistant is contacted, then greets (or says what is wrong). */
  function setupMoments() {
    const root = document.querySelector(".moment");
    const moments = A.robot.moments;
    moments.attach(root);
    moments.show({ kind: "load" }, { sticky: true });
    A.api.checkHealth().then((status) => {
      moments.showAfter(status === "ok" ? { kind: "greet" } : A.robot.momentForFailure(status), A.robot.MIN_LOAD_MS);
    });
    window.addEventListener("offline", () => moments.show({ kind: "net" }));
    window.addEventListener("keydown", (event) => {
      if (event.key === "Escape") moments.dismiss();
    });
  }

  /** "தமிழ் / English": the chat's words in the other language (remembered in this browser). */
  function setupLanguage() {
    const button = document.querySelector(".chat__lang");
    const mark = () => {
      if (button) button.setAttribute("lang", A.i18n.lang === "ta" ? "en" : "ta");
    };
    A.i18n.apply();
    mark();
    if (button) button.addEventListener("click", () => {
      A.i18n.toggle();
      mark();
    });
  }

  function boot() {
    setupLanguage();
    A.robot.drawProfiles();
    setupMenu();
    setupScrollToChat();
    setupMoments();
    const section = document.getElementById("assistant");
    if (section) A.page.chat = A.chat.setupChat(section);
  }

  A.page = { boot: boot };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})((window.Arivazhai = window.Arivazhai || {}));
