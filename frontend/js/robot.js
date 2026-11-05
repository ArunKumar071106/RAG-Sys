/*
 * Arivazhai the robot, from the design project's Moments.dc.html: one SVG rig whose moment class
 * (greet, think, error, net, unsure) switches its face and motion through css/robot.css (built into css/tailwind.css).
 *
 * Moments: the robot pops up over a blurred screen for about 2.5 s, then floats away. On page load
 * it waves with "Getting ready…" while the assistant is contacted, then says "Vanakkam!" (or that it
 * is offline). It pops up again while an answer is searched for, when the website has no answer,
 * and when something goes wrong.
 */
(function (A) {
  "use strict";

  let counter = 0;

  /** The robot as SVG markup. face: a moment kind (omitted: resting face); crop "head" for the profile picture. */
  function robotSvg(face, crop) {
    const uid = "rb" + (++counter).toString(36);
    const viewBox = crop === "head" ? "18 0 204 160" : "0 0 240 260";
    return (
      '<svg class="rb' + (face ? " " + face : "") + '" viewBox="' + viewBox + '" width="100%" height="100%" aria-hidden="true" focusable="false"' +
      (face ? ' data-face="' + face + '"' : "") + ">" +
      `<defs><radialGradient id="${uid}Body" cx="0.36" cy="0.26" r="0.9"><stop offset="0" stop-color="#FFFFFF"></stop><stop offset="0.5" stop-color="#EEF2F8"></stop><stop offset="0.85" stop-color="#C5CFDD"></stop><stop offset="1" stop-color="#9AA9BF"></stop></radialGradient><radialGradient id="${uid}Silver" cx="0.35" cy="0.3" r="0.8"><stop offset="0" stop-color="#FFFFFF"></stop><stop offset="1" stop-color="#A3B1C6"></stop></radialGradient><radialGradient id="${uid}Screen" cx="0.5" cy="0.35" r="0.75"><stop offset="0" stop-color="#1E3B7C"></stop><stop offset="1" stop-color="#070F27"></stop></radialGradient><linearGradient id="${uid}Eye" x1="0" y1="0" x2="0" y2="1"><stop offset="0" stop-color="#D6FEFF"></stop><stop offset="0.45" stop-color="#6CF0FF"></stop><stop offset="1" stop-color="#1FB8E6"></stop></linearGradient><radialGradient id="${uid}Glow" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#6CF0FF" stop-opacity="0.85"></stop><stop offset="1" stop-color="#6CF0FF" stop-opacity="0"></stop></radialGradient><radialGradient id="${uid}PadG" cx="0.5" cy="0.5" r="0.5"><stop offset="0" stop-color="#6CF0FF" stop-opacity="0.6"></stop><stop offset="0.6" stop-color="#3FA9FF" stop-opacity="0.18"></stop><stop offset="1" stop-color="#3FA9FF" stop-opacity="0"></stop></radialGradient><filter id="${uid}Blur" x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="3.2"></feGaussianBlur></filter></defs><g class="fx fx-load"><circle cx="120" cy="138" r="112" fill="none" stroke="#6CF0FF" stroke-opacity="0.15" stroke-width="3"></circle><circle class="spinner" cx="120" cy="138" r="112" fill="none" stroke="#6CF0FF" stroke-width="3.5" stroke-linecap="round" stroke-dasharray="120 584"></circle></g><ellipse class="pad" cx="120" cy="250" rx="58" ry="10" fill="url(#${uid}PadG)"></ellipse><g class="float"><g class="squash"><path class="ring ring-dash" d="M48 200 A72 15 0 0 1 192 200" fill="none" stroke="#6CF0FF" stroke-width="2" stroke-opacity="0.4" stroke-dasharray="5 7" stroke-linecap="round"></path><rect x="106" y="150" width="28" height="12" rx="6" fill="#A3B1C6"></rect><path d="M70 182 C70 152 170 152 170 182 C170 218 148 240 120 240 C92 240 70 218 70 182 Z" fill="url(#${uid}Body)"></path><path d="M160 174 C167 192 161 216 141 232" fill="none" stroke="#8FF4FF" stroke-width="2.5" stroke-linecap="round" opacity="0.6"></path><ellipse cx="120" cy="198" rx="30" ry="26" fill="#FFFFFF" opacity="0.5"></ellipse><circle class="core-glow" cx="120" cy="192" r="22" fill="url(#${uid}Glow)"></circle><circle cx="120" cy="192" r="12" fill="#0D1B3D" stroke="#F5B800" stroke-width="2.5"></circle><g class="core-spin"><path d="M120 184 A8 8 0 0 1 128 192" fill="none" stroke="#6CF0FF" stroke-width="2" stroke-linecap="round"></path><path d="M120 200 A8 8 0 0 1 112 192" fill="none" stroke="#6CF0FF" stroke-width="2" stroke-linecap="round"></path></g><circle class="core" cx="120" cy="192" r="4.5" fill="#6CF0FF"></circle><path class="ring ring-dash" d="M48 200 A72 15 0 0 0 192 200" fill="none" stroke="#6CF0FF" stroke-width="2.2" stroke-opacity="0.8" stroke-dasharray="5 7" stroke-linecap="round"></path><g class="hand hand-l"><ellipse cx="44" cy="188" rx="12.5" ry="15.5" fill="url(#${uid}Silver)" transform="rotate(-14 44 188)"></ellipse><ellipse cx="46" cy="198" rx="7" ry="3" fill="#F5B800" opacity="0.9" transform="rotate(-14 46 198)"></ellipse></g><g class="hand hand-r"><ellipse cx="196" cy="188" rx="12.5" ry="15.5" fill="url(#${uid}Silver)" transform="rotate(14 196 188)"></ellipse><ellipse cx="194" cy="198" rx="7" ry="3" fill="#F5B800" opacity="0.9" transform="rotate(14 194 198)"></ellipse></g><g class="hfollow"><g class="head"><g class="antenna"><path d="M120 38 Q117 28 121 20" fill="none" stroke="#A3B1C6" stroke-width="4" stroke-linecap="round"></path><circle class="tip" cx="121" cy="16" r="13" fill="url(#${uid}Glow)"></circle><circle cx="121" cy="16" r="6" fill="url(#${uid}Eye)" stroke="#F5B800" stroke-width="1.5"></circle></g><circle cx="38" cy="96" r="15" fill="url(#${uid}Silver)"></circle><circle cx="38" cy="96" r="9" fill="none" stroke="#F5B800" stroke-width="3"></circle><circle class="ear-light" cx="38" cy="96" r="4" fill="#6CF0FF"></circle><circle cx="202" cy="96" r="15" fill="url(#${uid}Silver)"></circle><circle cx="202" cy="96" r="9" fill="none" stroke="#F5B800" stroke-width="3"></circle><circle class="ear-light" cx="202" cy="96" r="4" fill="#6CF0FF"></circle><rect x="38" y="34" width="164" height="122" rx="56" fill="url(#${uid}Body)"></rect><path d="M190 62 Q206 96 188 140" fill="none" stroke="#8FF4FF" stroke-width="3" stroke-linecap="round" opacity="0.55"></path><ellipse cx="84" cy="48" rx="28" ry="8" fill="#FFFFFF" opacity="0.95" transform="rotate(-10 84 48)"></ellipse><rect x="54" y="52" width="132" height="88" rx="40" fill="url(#${uid}Screen)"></rect><path d="M68 84 Q74 62 104 59" fill="none" stroke="#FFFFFF" stroke-width="6" stroke-linecap="round" opacity="0.13"></path><g class="look"><g class="e-open" filter="url(#${uid}Blur)" opacity="0.75"><rect x="80" y="76" width="24" height="32" rx="12" fill="#6CF0FF"></rect><rect x="136" y="76" width="24" height="32" rx="12" fill="#6CF0FF"></rect></g><g class="eyes e-open"><rect x="80" y="76" width="24" height="32" rx="12" fill="url(#${uid}Eye)"></rect><rect class="eye-r" x="136" y="76" width="24" height="32" rx="12" fill="url(#${uid}Eye)"></rect><circle cx="97" cy="85" r="4.5" fill="#FFFFFF"></circle><circle cx="153" cy="85" r="4.5" fill="#FFFFFF"></circle></g><g class="e-happy"><path d="M80 100 Q92 78 104 100 M136 100 Q148 78 160 100" fill="none" stroke="#9FF7FF" stroke-width="6.5" stroke-linecap="round"></path></g><g class="e-flat"><rect x="80" y="90" width="24" height="7" rx="3.5" fill="#6CF0FF" opacity="0.5"></rect><rect x="136" y="90" width="24" height="7" rx="3.5" fill="#6CF0FF" opacity="0.5"></rect></g><g class="e-load"><circle class="spin-eye" cx="92" cy="92" r="12" fill="none" stroke="#6CF0FF" stroke-width="5" stroke-linecap="round" stroke-dasharray="44 32"></circle><circle class="spin-eye spin-eye2" cx="148" cy="92" r="12" fill="none" stroke="#6CF0FF" stroke-width="5" stroke-linecap="round" stroke-dasharray="44 32"></circle></g><g class="e-squeeze"><path d="M82 82 L102 92 L82 102 M158 82 L138 92 L158 102" fill="none" stroke="#9FF7FF" stroke-width="6" stroke-linecap="round" stroke-linejoin="round"></path></g><g class="e-dot"><circle cx="92" cy="92" r="8" fill="url(#${uid}Eye)"></circle><circle cx="148" cy="92" r="8" fill="url(#${uid}Eye)"></circle><circle cx="95" cy="89" r="2.5" fill="#FFFFFF"></circle><circle cx="151" cy="89" r="2.5" fill="#FFFFFF"></circle></g></g><g class="brows"><path class="brow-l" d="M80 68 Q92 63 104 67" fill="none" stroke="#9FF7FF" stroke-width="4" stroke-linecap="round"></path><path class="brow-r" d="M136 62 Q148 55 160 61" fill="none" stroke="#9FF7FF" stroke-width="4" stroke-linecap="round"></path></g><ellipse class="blush" cx="72" cy="120" rx="9" ry="5" fill="#FF8FC0" opacity="0.4"></ellipse><ellipse class="blush" cx="168" cy="120" rx="9" ry="5" fill="#FF8FC0" opacity="0.4"></ellipse><path class="sweat" d="M176 58 Q182 68 176 73 Q170 68 176 58 Z" fill="#5FC9E8"></path><rect class="scanline" x="56" y="54" width="128" height="8" rx="4" fill="#9FF7FF" opacity="0.14"></rect><path class="m-smile" d="M104 118 Q120 130 136 118" fill="none" stroke="#9FF7FF" stroke-width="5" stroke-linecap="round"></path><g class="m-open"><path d="M102 115 Q120 140 138 115 Q120 122 102 115 Z" fill="#9FF7FF"></path><path d="M112 127 Q120 133 128 127 Q120 124 112 127 Z" fill="#FF8FC0" opacity="0.85"></path></g><ellipse class="m-o" cx="120" cy="122" rx="6" ry="6" fill="none" stroke="#9FF7FF" stroke-width="4"></ellipse><path class="m-wavy" d="M106 122 Q113 117 120 122 Q127 127 134 122" fill="none" stroke="#9FF7FF" stroke-width="4" stroke-linecap="round"></path><path class="m-flat" d="M108 122 H132" fill="none" stroke="#9FF7FF" stroke-width="4" stroke-linecap="round" opacity="0.55"></path><g class="m-dots"><circle class="md md1" cx="108" cy="122" r="3.5" fill="#9FF7FF"></circle><circle class="md md2" cx="120" cy="122" r="3.5" fill="#9FF7FF"></circle><circle class="md md3" cx="132" cy="122" r="3.5" fill="#9FF7FF"></circle></g><path class="m-frown" d="M106 127 Q120 116 134 127" fill="none" stroke="#9FF7FF" stroke-width="5" stroke-linecap="round"></path></g></g></g><g class="fx fx-think"><circle class="orb orb1" cx="120" cy="40" r="5" fill="#6CF0FF"></circle><circle class="orb orb2" cx="120" cy="40" r="4" fill="#9FF7FF"></circle><circle class="orb orb3" cx="120" cy="40" r="3.5" fill="#3FA9FF"></circle></g><g class="fx fx-burst"><path class="bst bst1" d="M30 39 Q31.4 44.6 37 46 Q31.4 47.4 30 53 Q28.6 47.4 23 46 Q28.6 44.6 30 39 Z" fill="#9FF7FF"></path><path class="bst bst2" d="M210 31 Q211.8 38.2 219 40 Q211.8 41.8 210 49 Q208.2 41.8 201 40 Q208.2 38.2 210 31 Z" fill="#F5B800"></path><path class="bst bst3" d="M218 122 Q219.2 126.8 224 128 Q219.2 129.2 218 134 Q216.8 129.2 212 128 Q216.8 126.8 218 122 Z" fill="#FFD27A"></path><path class="bst bst4" d="M22 130 Q23.2 134.8 28 136 Q23.2 137.2 22 142 Q20.8 137.2 16 136 Q20.8 134.8 22 130 Z" fill="#FF8FC0"></path></g><g class="fx fx-unsure"><g class="bob"><circle cx="208" cy="32" r="16" fill="#F5A524" fill-opacity="0.2" stroke="#FFB84D" stroke-width="2.2"></circle><path d="M203 27 Q203 21 208 21 Q213 21 213 26 Q213 30 208 32 V35" fill="none" stroke="#FFC566" stroke-width="2.8" stroke-linecap="round"></path><circle cx="208" cy="40.5" r="1.9" fill="#FFC566"></circle></g></g><g class="fx fx-error"><circle cx="208" cy="32" r="16" fill="#F5A524" fill-opacity="0.2" stroke="#FFB84D" stroke-width="2.2"></circle><path d="M208 24 V34" fill="none" stroke="#FFC566" stroke-width="3" stroke-linecap="round"></path><circle cx="208" cy="40" r="1.9" fill="#FFC566"></circle></g><g class="fx fx-net"><circle cx="208" cy="32" r="16" fill="#F5A524" fill-opacity="0.2" stroke="#FFB84D" stroke-width="2.2"></circle><path d="M199 30 Q208 22 217 30 M202.5 34 Q208 29.5 213.5 34" fill="none" stroke="#FFC566" stroke-width="2.4" stroke-linecap="round"></path><circle cx="208" cy="38.5" r="1.9" fill="#FFC566"></circle><path d="M200 22 L216 42" fill="none" stroke="#FFC566" stroke-width="2.4" stroke-linecap="round"></path></g></g>` +
      "</svg>"
    );
  }

  const officePhone = A.site && A.site.officePhones[0];

  /** From the design: 0.35 s fade and blur in, about 2.2 s hold, 0.4 s exit. */
  const ENTER_MS = 350;
  const HOLD_MS = 2200;
  const EXIT_MS = 400;
  /** The loading moment stays at least this long, so it never just flickers. */
  const MIN_LOAD_MS = 1000;

  /** Loading uses the welcome hop and wave: the robot is already greeting while the assistant is contacted. */
  const FACE = { greet: "greet", load: "greet", think: "think", error: "error", net: "net", unsure: "unsure" };

  const TEXT = {
    greet: { title: "Vanakkam! I'm Arivazhai", text: "Your guide to AAACET admissions. Ask me anything." },
    load: { title: "Getting ready…", text: "Loading the official AAACET website content." },
    think: { title: "Finding your answer…", text: "Searching the official AAACET website." },
    error: { title: "Something went wrong", text: "Please try again in a moment." },
    net: { title: "You're offline", text: "Check your connection and try again." },
    unsure: {
      title: "I couldn't find that",
      text: officePhone ? "Call the admission office: " + officePhone : "The admission office can help you directly.",
    },
  };

  const isOffline = () => typeof navigator !== "undefined" && navigator.onLine === false;

  /** The moment for a failed request, worded for what actually went wrong. */
  function momentForFailure(kind) {
    if (isOffline()) return { kind: "net" };
    switch (kind) {
      case "network":
        return { kind: "error", title: "Can't reach the assistant", text: "Please check your connection and try again." };
      case "timeout":
        return { kind: "error", title: "That took too long", text: "Please try again in a moment." };
      case "rate_limited":
        return { kind: "error", title: "Too many questions at once", text: "Please wait a moment and try again." };
      case "starting":
        return { kind: "error", title: "Still getting ready", text: "Please try again in a minute." };
      case "invalid":
        return { kind: "unsure", title: "Could you rephrase that?", text: "Ask about admissions, courses, fees or campus life." };
      default:
        return { kind: "error" };
    }
  }

  /** Only an answer that is not on the website gets a moment; a real answer is simply shown. */
  function momentForResult(result) {
    return result.mode === "no_answer" ? { kind: "unsure" } : null;
  }

  /** One moment at a time over the page: a newer one replaces the one on screen. Sticky ones (loading) stay until replaced. */
  const moments = {
    root: null,
    current: null,
    leaving: false,
    shownAt: 0,
    timers: [],

    attach(root) {
      this.root = root;
    },

    show(cue, options) {
      this.clearTimers();
      const base = TEXT[cue.kind];
      // loading turns into the welcome without the robot popping in again: it is already waving
      const continues = this.current && this.current.kind === "load" && cue.kind === "greet" && !this.leaving;
      this.current = { kind: cue.kind, title: cue.title || base.title, text: cue.text || base.text };
      this.leaving = false;
      this.shownAt = Date.now();
      this.draw(continues);
      if (!(options && options.sticky)) this.timers.push(setTimeout(() => this.dismiss(), ENTER_MS + HOLD_MS));
    },

    /** Replace a sticky moment once it has been on screen for at least minMs. */
    showAfter(cue, minMs) {
      const wait = Math.max(0, this.shownAt + minMs - Date.now());
      if (!this.current || wait === 0) return this.show(cue);
      this.clearTimers();
      this.timers.push(setTimeout(() => this.show(cue), wait));
    },

    /** Float away now (Esc, or the hold is over). */
    dismiss() {
      if (!this.current || this.leaving) return;
      this.clearTimers();
      this.leaving = true;
      this.draw(true);
      this.timers.push(
        setTimeout(() => {
          this.current = null;
          this.leaving = false;
          this.draw(false);
        }, EXIT_MS),
      );
    },

    get kind() {
      return this.current ? this.current.kind : null;
    },

    clearTimers() {
      this.timers.forEach(clearTimeout);
      this.timers = [];
    },

    /** keep: update the words and classes without restarting the robot's entrance. */
    draw(keep) {
      const root = this.root;
      if (!root) return;
      root.classList.toggle("is-shown", !!this.current);
      root.classList.toggle("is-leaving", this.leaving);
      if (!this.current) {
        root.textContent = "";
        return;
      }
      const m = this.current;
      let mov = root.querySelector(".mov");
      if (!keep || !mov) {
        root.textContent = "";
        mov = document.createElement("div");
        mov.className = "mov animate-moment-in [.is-leaving_&]:animate-moment-out";
        const robot = document.createElement("div");
        robot.className = "moment__robot aspect-[240/260] w-[clamp(170px,22vw,220px)] animate-moment-pop motion-reduce:animate-none [.is-leaving_&]:animate-moment-float motion-reduce:[.is-leaving_&]:animate-none";
        robot.innerHTML = robotSvg(FACE[m.kind]); // our own SVG markup, no outside text
        const title = document.createElement("p");
        title.className = "moment__title mt-2 mb-0 text-center font-heading text-[clamp(1.3rem,2.4vw,1.7rem)] font-bold text-white";
        const text = document.createElement("p");
        text.className = "moment__text m-0 max-w-[34ch] text-center text-[0.95rem] text-mist";
        mov.append(robot, title, text);
        root.appendChild(mov);
      } else {
        const svg = mov.querySelector("svg");
        svg.setAttribute("class", "rb " + FACE[m.kind]);
        svg.setAttribute("data-face", FACE[m.kind]);
      }
      mov.setAttribute("data-moment", m.kind);
      mov.querySelector(".moment__title").textContent = m.title;
      mov.querySelector(".moment__text").textContent = m.text;
    },
  };

  /** Fill every element marked data-robot="head" with the robot's face (the profile pictures). */
  function drawProfiles(scope) {
    (scope || document).querySelectorAll("[data-robot]").forEach((node) => {
      if (!node.firstChild) node.innerHTML = robotSvg(undefined, node.getAttribute("data-robot"));
    });
  }

  A.robot = { robotSvg, drawProfiles, moments, momentForFailure, momentForResult, TEXT, MIN_LOAD_MS, ENTER_MS, HOLD_MS, EXIT_MS };
})((window.Arivazhai = window.Arivazhai || {}));
