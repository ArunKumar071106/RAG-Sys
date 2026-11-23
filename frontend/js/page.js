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
        document.documentElement.classList.toggle("menu-open", open);
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

  /**
   * Phones: the chat fills the screen like a chat app. Its height follows the visible part of the
   * screen (the browser's bars and the on-screen keyboard come and go), so the question box stays
   * just above the keyboard.
   */
  function setupAppHeight() {
    const view = window.visualViewport;
    if (!view) return;
    const set = () => {
      document.documentElement.style.setProperty("--app-height", Math.round(view.height) + "px");
      // iOS scrolls the page when the keyboard opens; on a phone the page itself never needs to scroll
      if (window.scrollY && window.matchMedia && window.matchMedia("(max-width: 760px)").matches) window.scrollTo(0, 0);
    };
    view.addEventListener("resize", set);
    set();
  }

  /** Phones: the ☰ menu slides out the help panel (who is chatting, admission help, map, college pages). */
  function setupDrawer() {
    const button = document.querySelector(".chat__menu");
    const panel = document.getElementById("help-panel");
    if (!button || !panel) return;
    const root = document.documentElement;
    const close = panel.querySelector(".drawer__close");
    const backdrop = document.querySelector(".drawer-backdrop");
    const setOpen = (open) => {
      root.classList.toggle("drawer-open", open);
      button.setAttribute("aria-expanded", String(open));
      if (open) (close || panel).focus();
      else if (panel.contains(document.activeElement)) button.focus();
    };
    button.addEventListener("click", () => setOpen(!root.classList.contains("drawer-open")));
    if (close) close.addEventListener("click", () => setOpen(false));
    if (backdrop) backdrop.addEventListener("click", () => setOpen(false));
    document.addEventListener("keydown", (event) => {
      if (event.key === "Escape" && root.classList.contains("drawer-open")) setOpen(false);
    });
    panel.addEventListener("click", (event) => {
      if (event.target.closest("a")) setOpen(false); // a link was followed
    });

    // who is chatting, and "Not you?", in the menu
    const who = panel.querySelector(".drawer__user");
    const signOut = panel.querySelector(".drawer__signout");
    const show = (user) => {
      root.classList.toggle("has-user", !!user);
      if (who) who.textContent = user ? A.i18n.t("who") + " " + user.name : "";
    };
    if (A.user) {
      show(A.user.current());
      A.user.onChange(show);
      if (signOut) signOut.addEventListener("click", () => {
        setOpen(false);
        A.user.signOut();
      });
    }
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
    setupAppHeight();
    setupDrawer();
    setupScrollToChat();
    setupMoments();
    const section = document.getElementById("assistant");
    if (section) A.page.chat = A.chat.setupChat(section);
  }

  A.page = { boot: boot };
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", boot);
  else boot();
})((window.Arivazhai = window.Arivazhai || {}));
