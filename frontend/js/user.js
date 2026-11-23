/*
 * Who is chatting, and their conversation, kept in this browser only.
 *
 * Before the first question the chat asks for a name and a mobile number (POST /api/users). The server
 * saves them for the admission office and returns a signed token, which every question then carries
 * (header X-Arivazhai-User). Here we keep the name and the token, never the phone number.
 *
 * The conversation is saved per person in this browser (localStorage) and comes back after a reload;
 * "New chat" deletes it. Storage can be blocked (private windows): then nothing is remembered, and
 * the chat still works.
 */
(function (A) {
  "use strict";

  const USER_KEY = "arivazhai-user";
  const HISTORY_PREFIX = "arivazhai-history-";
  const MAX_MESSAGES = 40; // the last 20 questions and answers

  function read(key) {
    try {
      const raw = window.localStorage.getItem(key);
      return raw ? JSON.parse(raw) : null;
    } catch (e) {
      return null;
    }
  }

  function write(key, value) {
    try {
      if (value === null) window.localStorage.removeItem(key);
      else window.localStorage.setItem(key, JSON.stringify(value));
      return true;
    } catch (e) {
      return false; // blocked or full: not remembered
    }
  }

  function current() {
    const user = read(USER_KEY);
    return user && typeof user.token === "string" && typeof user.name === "string" ? user : null;
  }

  function idOf(user) {
    return user ? String(user.token).split(".")[0] : "";
  }

  const listeners = [];

  function changed() {
    listeners.forEach((fn) => fn(current()));
  }

  /** Check the name and number here first, so most mistakes are shown without a round trip. */
  function validate(name, phone) {
    const t = A.i18n ? A.i18n.t : (k) => k;
    const cleanName = String(name || "").replace(/\s+/g, " ").trim();
    let digits = String(phone || "").replace(/[\s()-]/g, "");
    if (digits.startsWith("+91")) digits = digits.slice(3);
    else if (digits.length === 12 && digits.startsWith("91")) digits = digits.slice(2);
    else if (digits.length === 11 && digits.startsWith("0")) digits = digits.slice(1);
    const errors = {};
    if (cleanName.length < 2 || cleanName.length > 60 || /[\d<>{}[\]@#$%^&*_=+|\\/~`"!?;:]/.test(cleanName)) errors.name = t("loginNameError");
    if (!/^[6-9]\d{9}$/.test(digits)) errors.phone = t("loginPhoneError");
    return { name: cleanName, phone: digits, errors: errors };
  }

  async function signIn(name, phone) {
    const response = await fetch(A.api.apiUrl("/api/users"), {
      method: "POST",
      headers: { "Content-Type": "application/json" },
      body: JSON.stringify({ name: name, phone: phone }),
    });
    if (!response.ok) {
      let detail = "";
      try {
        detail = (await response.json()).detail;
      } catch (e) {
        /* not JSON */
      }
      const error = new Error(typeof detail === "string" && detail ? detail : A.i18n.t("loginFailed"));
      error.status = response.status;
      throw error;
    }
    const body = await response.json();
    write(USER_KEY, { name: body.name, token: body.token });
    changed();
    return current();
  }

  function signOut() {
    write(USER_KEY, null); // their saved chat stays for when they sign in again on this device
    changed();
  }

  const history = {
    load() {
      const saved = read(HISTORY_PREFIX + idOf(current()));
      return Array.isArray(saved) ? saved : [];
    },
    save(messages) {
      const user = current();
      if (!user) return;
      const kept = messages.filter((m) => m && (m.role === "user" || (m.role === "assistant" && !m.error))).slice(-MAX_MESSAGES);
      // a full storage drops the oldest turns first
      for (let from = 0; from < kept.length; from += 2) {
        if (write(HISTORY_PREFIX + idOf(user), kept.slice(from))) return;
      }
    },
    clear() {
      const user = current();
      if (user) write(HISTORY_PREFIX + idOf(user), null);
    },
  };

  A.user = {
    current: current,
    token: () => (current() || {}).token || "",
    validate: validate,
    signIn: signIn,
    signOut: signOut,
    onChange: (fn) => listeners.push(fn),
    history: history,
  };
})((window.Arivazhai = window.Arivazhai || {}));
