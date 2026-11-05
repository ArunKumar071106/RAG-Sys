/*
 * The chat: questions, answers (with their sources, photos and the college's contacts), "Try
 * again" after a failure, "New chat", suggested next questions, and the question box with
 * suggestions while typing. The robot's moments follow each request as it really happens.
 */
(function (A) {
  "use strict";

  const api = A.api;
  const robot = A.robot;
  const site = A.site;

  /** The API reads the last 12 turns, the first 2,000 characters of each. */
  const HISTORY_LIMIT = 12;
  const HISTORY_TURN_CHARS = 2000;
  const MAX_MESSAGE_LENGTH = 1000;
  const SUGGEST_DELAY_MS = 150;

  /** Questions asking to see pictures (the same words the API looks for). */
  const PHOTO_QUESTION = /\b(photos?|pictures?|pics?|images?|gallery|posters?|show me|look(s)? like|view of)\b/i;
  /** Questions whose answer ends with the ways to reach the college. */
  const CONTACT_QUESTION = /\b(contact|phone|call|mobile|number|e-?mail|mail|enquir|inquir|reach|address|helpline|office)/i;
  /** Questions the admission and scholarship staff answer. */
  const ADMISSION_QUESTION = /\b(admission|admit|apply|application|counsell?ing|scholarship|fees?|quota|seat|eligib|join)/i;

  // ------------------------------------------------------------------ small helpers
  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) {
      for (const key of Object.keys(attrs)) {
        const value = attrs[key];
        if (value == null || value === false) continue;
        if (key === "text") node.textContent = value;
        else if (key === "onclick") node.addEventListener("click", value);
        else node.setAttribute(key, value === true ? "" : value);
      }
    }
    for (const child of children || []) if (child != null && child !== false) node.append(child);
    return node;
  }

  const safeHref = (href) => A.markdown.safeHref(href);
  const hidden = (text) => el("span", { class: "visually-hidden", text: text });

  /** "18004258807" -> "1800 425 8807"; other numbers as the website writes them. */
  function formatPhone(phone) {
    const digits = phone.replace(/\D/g, "");
    return /^1800\d{7}$/.test(digits) ? digits.slice(0, 4) + " " + digits.slice(4, 7) + " " + digits.slice(7) : phone;
  }
  const telHref = (phone) => "tel:" + phone.replace(/[^\d+]/g, "");

  let counter = 0;
  const nextId = () => "m" + Date.now().toString(36) + (counter++).toString(36);

  /** The conversation sent with a question: successful turns only, most recent last. */
  function historyFrom(messages) {
    return messages
      .filter((m) => !m.error && m.content.trim())
      .map((m) => ({ role: m.role, content: m.content.slice(0, HISTORY_TURN_CHARS) }))
      .slice(-HISTORY_LIMIT);
  }

  const escapeTitle = (text) => text.replace(/["\\]/g, "\\$&").replace(/[\r\n]+/g, " ");

  /**
   * The backend's citation marks as Markdown links:
   *   [S2] -> [[2]](https://official/page "Source 2: Page title")
   *   [I1] -> [[image 1]](#<prefix>-I1)   (jumps to the image card)
   * Unknown marks are removed rather than shown as dead links.
   */
  function linkCitations(answer, sources, images, prefix) {
    const byId = new Map(sources.map((s) => [s.id, s]));
    const imageIds = new Set(images.map((i) => i.id));
    return answer.replace(/\[(S|I)(\d+)\]/g, (match, kind, num) => {
      if (kind === "S") {
        const source = byId.get("S" + num);
        return source ? "[[" + num + "]](" + source.url + ' "Source ' + num + ": " + escapeTitle(source.title) + '")' : "";
      }
      return imageIds.has("I" + num) ? "[[image " + num + "]](#" + prefix + "-I" + num + ")" : "";
    });
  }

  // ------------------------------------------------------------------ pieces of an answer
  function sender() {
    const profile = el("span", { class: "profile profile--small", "data-robot": "head" });
    robot.drawProfiles(el("div", null, [profile]));
    return el("span", { class: "message__sender", "aria-hidden": "true" }, [profile, "Arivazhai"]);
  }

  /** Clickable questions: the welcome's "Try asking" and the "You can also ask" under an answer. */
  function suggestionList(questions, title, onSelect) {
    const titleId = nextId();
    return el("div", { class: "suggestions" }, [
      el("h3", { class: "suggestions__title", id: titleId, text: title }),
      el(
        "ul",
        { class: "suggestions__list", "aria-labelledby": titleId },
        questions.map((q) => el("li", null, [el("button", { type: "button", class: "chip", "data-busy": true, text: q, onclick: () => onSelect(q) })])),
      ),
    ]);
  }

  function sourceList(sources, title, variant) {
    if (!sources.length) return null;
    return el("section", { class: "sources sources--" + variant, "aria-label": title }, [
      el("h4", { class: "sources__title", text: title }),
      el(
        "ol",
        { class: "sources__list" },
        sources.map((source, index) => {
          const href = safeHref(source.url);
          const label = href
            ? el("a", { href: href, target: "_blank", rel: "noopener noreferrer", class: "sources__link" }, [
                source.title,
                source.heading ? el("span", { class: "sources__heading", text: " - " + source.heading }) : null,
                hidden(" (opens official page in a new tab)"),
              ])
            : el("span", { class: "sources__link", text: source.title });
          return el("li", { class: "sources__item" }, [
            variant === "cited" ? el("span", { class: "sources__num", "aria-hidden": "true", text: String(index + 1) }) : null,
            el("div", { class: "sources__body" }, [label, source.snippet ? el("p", { class: "sources__snippet", text: source.snippet }) : null]),
          ]);
        }),
      ),
    ]);
  }

  /** A photo from the website: our API's copy first, then the original address, then a placeholder. */
  function imageCard(image, index, anchorId) {
    const alt = image.alt || image.caption || 'Image from the page "' + image.page_title + '"';
    const title = image.caption || image.alt || image.heading || image.page_title;
    const meta = [image.page_title, image.heading].filter((part, i, all) => part && part !== title && all.indexOf(part) === i).join(" - ");
    const pageHref = safeHref(image.source_page);
    const originalHref = safeHref(image.original_url);

    const frame = el("div", { class: "image-card__frame" });
    if (image.width && image.height) frame.style.aspectRatio = image.width + " / " + image.height;
    const img = el("img", { src: api.apiUrl(image.src), alt: alt, loading: "lazy", decoding: "async" });
    let triedOriginal = false;
    img.addEventListener("error", () => {
      if (!triedOriginal && originalHref) {
        triedOriginal = true;
        img.src = originalHref;
        return;
      }
      const missing = el("div", { class: "image-card__missing", role: "img", "aria-label": "Image unavailable: " + alt }, [el("span", { text: "Image unavailable" })]);
      missing.insertAdjacentHTML(
        "afterbegin",
        '<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" focusable="false"><path fill="currentColor" d="M21 5v14H3V5h18m0-2H3a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h18a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm-7.5 9.5-3 3.9-2-2.6L5.5 17h13l-5-4.5z"/></svg>',
      );
      img.replaceWith(missing);
    });
    frame.append(img, el("span", { class: "image-card__badge", text: "Image " + index }));

    const links = el("span", { class: "image-card__links" }, [
      pageHref ? el("a", { href: pageHref, target: "_blank", rel: "noopener noreferrer" }, ["View source page", hidden(" (opens in a new tab)")]) : null,
      originalHref ? el("a", { href: originalHref, target: "_blank", rel: "noopener noreferrer" }, ["Open image", hidden(" (opens in a new tab)")]) : null,
    ]);
    const caption = el("figcaption", { class: "image-card__caption" }, [
      el("span", { class: "image-card__title", text: title }),
      meta ? el("span", { class: "image-card__meta", text: meta }) : null,
      image.ocr_text
        ? el("details", { class: "image-card__details" }, [el("summary", { text: "Text in image (OCR)" }), el("p", { class: "image-card__ocr", text: image.ocr_text })])
        : null,
      image.description_is_ai_generated && image.description
        ? el("p", { class: "image-card__ai" }, [el("span", { class: "tag tag--ai", text: "AI-generated description" }), " " + image.description])
        : null,
      links,
    ]);
    return el("figure", { class: "image-card", id: anchorId }, [frame, caption]);
  }

  /** How to reach the college, as tap-to-call and email links; for admission questions also the admission staff. */
  function contactCard(title, staff) {
    const items = [];
    for (const phone of site.officePhones) {
      items.push(
        el("li", null, [
          el("span", { "aria-hidden": "true", text: "📞" }),
          " ",
          el("a", { href: telHref(phone), text: formatPhone(phone) }),
          /^1800/.test(phone.replace(/\D/g, "")) ? el("span", { class: "contact-card__note", text: " (toll-free)" }) : null,
        ]),
      );
    }
    for (const email of site.emails) {
      items.push(el("li", null, [el("span", { "aria-hidden": "true", text: "✉️" }), " ", el("a", { href: "mailto:" + email, text: email })]));
    }
    const card = el("section", { class: "contact-card", "aria-label": title }, [el("h4", { class: "contact-card__title", text: title }), el("ul", { class: "contact-card__list" }, items)]);
    if (staff && site.admissionStaff.length) {
      card.append(
        el("h5", { class: "contact-card__subtitle", text: "Admission & scholarship" }),
        el(
          "ul",
          { class: "contact-card__people" },
          site.admissionStaff.map((person) =>
            el("li", null, [
              el("span", { class: "contact-card__name" }, [person.name, person.role ? el("span", { class: "contact-card__role", text: person.role }) : null]),
              " ",
              el("a", { href: telHref(person.phone), text: person.phone }),
            ]),
          ),
        ),
      );
    }
    return card;
  }

  /** "Show in English" for an answer in another language; "Show original" switches back. */
  function translateToggle(text, show) {
    let english = null;
    let showing = false;
    const button = el("button", { type: "button", class: "translate__button", "aria-pressed": "false" });
    const label = (words) => {
      button.textContent = "";
      button.append(el("span", { "aria-hidden": "true", text: "🌐" }), " " + words);
    };
    label("Show in English");
    const box = el("div", { class: "translate" }, [button]);
    button.addEventListener("click", async () => {
      const error = box.querySelector(".translate__error");
      if (error) error.remove();
      if (showing || english) {
        showing = !showing;
        show(showing ? english : null);
        button.setAttribute("aria-pressed", String(showing));
        label(showing ? "Show original" : "Show in English");
        return;
      }
      button.disabled = true;
      label("Translating…");
      try {
        english = await api.translateAnswer(text);
        showing = true;
        show(english);
        button.setAttribute("aria-pressed", "true");
        label("Show original");
      } catch (err) {
        label("Show in English");
        box.append(el("span", { class: "translate__error", role: "alert", text: err instanceof api.ApiError ? err.message : "The English version is not available right now." }));
      } finally {
        button.disabled = false;
      }
    });
    return box;
  }

  // ------------------------------------------------------------------ messages
  function renderUser(message) {
    return el("div", { class: "message message--user" }, [
      el("div", { class: "bubble bubble--user" }, [hidden("You said: "), el("span", { dir: "auto", text: message.content })]),
    ]);
  }

  function renderError(message, onRetry) {
    const retry = el("button", { type: "button", class: "btn btn--outline btn--small", "data-busy": true, text: "Try again", onclick: () => onRetry(message.id) });
    return el("div", { class: "message message--assistant" }, [
      sender(),
      el("div", { class: "bubble bubble--assistant bubble--error" }, [
        el("div", { class: "error-message", role: "alert" }, [
          el("span", { class: "error-message__icon", "aria-hidden": "true", text: "!" }),
          el("p", { class: "error-message__text", text: message.error.message }),
          retry,
        ]),
      ]),
    ]);
  }

  function renderAnswer(message) {
    const result = message.result;
    const question = message.question || "";
    const noAnswer = result.mode === "no_answer";
    const images = result.images || [];
    const sources = result.sources || [];

    const markdown = el("div", { class: "markdown", dir: "auto" });
    const showText = (english) => {
      const text = english == null ? message.content : english;
      markdown.textContent = "";
      markdown.append(A.markdown.render(linkCitations(text, sources, images, message.id)));
      if (english == null) markdown.removeAttribute("lang");
      else markdown.setAttribute("lang", "en");
    };
    showText(null);

    // "show me photos of the hostel": the photos are the answer, so they come before the text
    const photoQuestion = PHOTO_QUESTION.test(question);
    const gallery = images.length
      ? el("section", { class: "images", "aria-label": "Related images from the official website" }, [
          el("h4", { class: "images__title", text: "Images from the official website" }),
          el("div", { class: "images__grid" }, images.map((image, i) => imageCard(image, i + 1, message.id + "-" + image.id))),
        ])
      : null;
    // "not on the website" and contact questions end with how to reach the college
    const showContact = noAnswer || CONTACT_QUESTION.test(question);
    const showStaff = noAnswer || ADMISSION_QUESTION.test(question);
    const related = result.related_sources || [];

    return el("div", { class: "message message--assistant" }, [
      sender(),
      el("div", { class: "bubble bubble--assistant" + (noAnswer ? " bubble--no-answer" : "") }, [
        hidden("Assistant: "),
        photoQuestion ? gallery : null,
        markdown,
        result.translatable ? translateToggle(message.content, showText) : null,
        result.notice ? el("p", { class: "notice", text: result.notice }) : null,
        photoQuestion ? null : gallery,
        sourceList(sources, "Sources from the official website", "cited"),
        noAnswer && related.length ? sourceList(related, "These official pages may be related", "related") : null,
        showContact ? contactCard(noAnswer ? "The admission office can help you directly" : "Contact the college", showStaff) : null,
      ]),
    ]);
  }

  function renderLoading() {
    return el("div", { class: "message message--assistant", role: "status", "aria-live": "polite" }, [
      sender(),
      el("div", { class: "bubble bubble--assistant bubble--loading" }, [
        el("span", { class: "dots", "aria-hidden": "true" }, [el("span"), el("span"), el("span")]),
        el("span", { class: "loading-label", text: "Searching the official website…" }),
      ]),
    ]);
  }

  // ------------------------------------------------------------------ the question box
  /** The suggestion with the words that start like a typed word in bold. */
  function highlighted(text, typed) {
    const words = typed.toLowerCase().match(/[a-z0-9]+/g) || [];
    return text.split(/(\s+)/).map((part) => {
      const plain = part.toLowerCase().replace(/[^a-z0-9]/g, "");
      return plain && words.some((w) => plain.startsWith(w)) ? el("strong", { text: part }) : document.createTextNode(part);
    });
  }

  function setupInput(form, onSend, suggest) {
    const field = form.querySelector("textarea");
    const sendButton = form.querySelector(".chat-input__send");
    const list = form.querySelector(".chat-suggestions");
    const count = form.querySelector(".chat-input__count");
    let suggestions = [];
    let active = -1;
    let typed = false; // suggestions follow typing, not text set by picking one
    let timer = null;
    let request = null;
    let disabled = false;

    const trimmed = () => field.value.trim();
    const isOpen = () => !list.hidden && suggestions.length > 0;

    function refresh() {
      sendButton.disabled = !trimmed() || disabled;
      const remaining = MAX_MESSAGE_LENGTH - field.value.length;
      count.hidden = remaining > 100;
      count.textContent = " " + remaining + " characters left.";
    }

    function drawList() {
      list.textContent = "";
      const open = suggestions.length > 0 && !list.dataset.closed;
      list.hidden = !open;
      field.setAttribute("aria-expanded", String(open));
      if (open) field.setAttribute("aria-controls", list.id);
      else field.removeAttribute("aria-controls");
      field.removeAttribute("aria-activedescendant");
      suggestions.forEach((s, i) => {
        const item = el("li", { id: list.id + "-" + i, role: "option", "aria-selected": String(i === active), class: "chat-suggestions__item" + (i === active ? " is-active" : "") }, highlighted(s, field.value));
        item.addEventListener("mousedown", (e) => e.preventDefault()); // keep the focus in the box
        item.addEventListener("click", () => send(s));
        item.addEventListener("mouseenter", () => {
          active = i;
          drawList();
        });
        list.appendChild(item);
      });
      if (open && active >= 0) field.setAttribute("aria-activedescendant", list.id + "-" + active);
    }

    function close() {
      list.dataset.closed = "1";
      active = -1;
      drawList();
    }

    function clearSuggestions() {
      clearTimeout(timer);
      if (request) request.abort();
      request = null;
      suggestions = [];
      close();
    }

    function lookUp() {
      clearTimeout(timer);
      if (request) request.abort();
      const text = trimmed();
      if (!typed || text.length < 2) {
        suggestions = [];
        drawList();
        return;
      }
      const controller = new AbortController();
      request = controller;
      timer = setTimeout(() => {
        suggest(text, controller.signal).then((items) => {
          if (controller.signal.aborted) return;
          suggestions = items.filter((s) => s.toLowerCase() !== text.toLowerCase());
          active = -1;
          delete list.dataset.closed;
          drawList();
        });
      }, SUGGEST_DELAY_MS);
    }

    function send(text) {
      if (!text.trim() || disabled) return;
      onSend(text.trim());
      typed = false;
      field.value = "";
      clearSuggestions();
      refresh();
    }

    field.addEventListener("input", () => {
      typed = true;
      refresh();
      lookUp();
    });
    field.addEventListener("blur", close);
    field.addEventListener("keydown", (event) => {
      if (isOpen() && (event.key === "ArrowDown" || event.key === "ArrowUp")) {
        event.preventDefault();
        // -1 is "nothing picked" (Enter sends what was typed); the arrows cycle through it
        const last = suggestions.length - 1;
        if (event.key === "ArrowDown") active = active >= last ? -1 : active + 1;
        else active = active <= -1 ? last : active - 1;
        drawList();
        return;
      }
      if (isOpen() && event.key === "Escape") {
        event.preventDefault();
        close();
        return;
      }
      if (isOpen() && event.key === "Tab" && active >= 0) {
        event.preventDefault(); // take the suggestion into the box to edit it
        typed = false;
        field.value = suggestions[active];
        close();
        refresh();
        return;
      }
      if (event.key === "Enter" && !event.shiftKey && !event.isComposing) {
        event.preventDefault();
        if (isOpen() && active >= 0) send(suggestions[active]);
        else send(trimmed());
      }
    });
    form.addEventListener("submit", (event) => {
      event.preventDefault();
      send(trimmed());
    });
    refresh();

    return {
      field: field,
      setDisabled(value) {
        disabled = value;
        refresh();
      },
    };
  }

  // ------------------------------------------------------------------ the chat
  /** Event the "Chat below" arrow and the Arivazhai menu link send: the chat scrolls into view and takes focus. */
  const START_CHAT_EVENT = "arivazhai:start-chat";

  function startChat() {
    window.dispatchEvent(new Event(START_CHAT_EVENT));
  }

  function showMoment(event) {
    if (event.type === "retrieving") robot.moments.show({ kind: "think" });
    else if (event.type === "failed") robot.moments.show(robot.momentForFailure(event.kind));
    else {
      const cue = robot.momentForResult(event.result);
      if (cue) robot.moments.show(cue);
    }
  }

  function setupChat(section, options) {
    const opts = options || {};
    const log = section.querySelector(".chat__log");
    const newChat = section.querySelector(".chat__new");
    const welcome = section.querySelector("#welcome-suggestions");
    const input = setupInput(section.querySelector(".chat-input"), (q) => ask(q), opts.suggest || api.fetchSuggestions);
    const sendChat = opts.sendChat || api.sendChat;
    const onEvent = opts.onEvent || showMoment;

    const state = { messages: [], loading: false, controller: null };
    const nodes = new Map(); // message id -> its element
    let loadingNode = null;
    let followUps = null;

    if (welcome) {
      welcome.querySelectorAll(".chip").forEach((chip) => {
        chip.setAttribute("data-busy", "");
        chip.addEventListener("click", () => ask(chip.textContent.trim()));
      });
    }

    function scrollToEnd() {
      const last = log.lastElementChild;
      if (last && last.scrollIntoView) last.scrollIntoView({ block: "end", behavior: "smooth" });
    }

    /** While a question is out: no sending, no "Try again", no clickable questions. */
    function setLoading(value) {
      state.loading = value;
      input.setDisabled(value);
      section.querySelectorAll("[data-busy]").forEach((button) => (button.disabled = value));
      newChat.disabled = state.messages.length === 0 && !value;
      if (value && !loadingNode) {
        loadingNode = renderLoading();
        log.appendChild(loadingNode);
      } else if (!value && loadingNode) {
        loadingNode.remove();
        loadingNode = null;
      }
      drawFollowUps();
      scrollToEnd();
    }

    /** "You can also ask" under the latest answer, while no question is out. */
    function drawFollowUps() {
      if (followUps) followUps.remove();
      followUps = null;
      const latest = [...state.messages].reverse().find((m) => m.role === "assistant");
      const questions = latest && latest.result && latest.result.follow_ups;
      if (state.loading || !questions || !questions.length) return;
      followUps = suggestionList(questions, "You can also ask", ask);
      nodes.get(latest.id).appendChild(followUps);
    }

    function add(message) {
      state.messages.push(message);
      const node = message.role === "user" ? renderUser(message) : message.error ? renderError(message, retry) : renderAnswer(message);
      nodes.set(message.id, node);
      if (loadingNode) log.insertBefore(node, loadingNode);
      else log.appendChild(node);
      if (welcome) welcome.hidden = true;
      newChat.disabled = false;
    }

    async function request(question, history) {
      if (state.controller) state.controller.abort();
      const controller = new AbortController();
      state.controller = controller;
      setLoading(true);
      onEvent({ type: "retrieving" });
      try {
        const result = await sendChat(question, history, controller.signal);
        if (controller.signal.aborted) return;
        add({ id: nextId(), role: "assistant", content: result.answer, result: result, question: question });
        onEvent({ type: "answered", result: result });
      } catch (err) {
        if (controller.signal.aborted) return;
        const error = err instanceof api.ApiError ? { message: err.message, kind: err.kind } : { message: "Something went wrong. Please try again.", kind: "server" };
        add({ id: nextId(), role: "assistant", content: "", error: error, question: question });
        onEvent({ type: "failed", kind: error.kind });
      } finally {
        if (state.controller === controller) {
          state.controller = null;
          setLoading(false);
        }
      }
    }

    function ask(text) {
      const question = String(text || "").trim();
      if (!question || state.controller) return;
      const history = historyFrom(state.messages);
      add({ id: nextId(), role: "user", content: question });
      request(question, history);
      input.field.focus();
    }

    function retry(errorId) {
      const failed = state.messages.find((m) => m.id === errorId);
      if (!failed || !failed.question || state.controller) return;
      state.messages = state.messages.filter((m) => m.id !== errorId);
      nodes.get(errorId).remove();
      nodes.delete(errorId);
      // the history leaves out the question itself, the last user turn
      request(failed.question, historyFrom(state.messages).slice(0, -1));
    }

    function reset() {
      if (state.controller) state.controller.abort();
      state.controller = null;
      state.messages = [];
      nodes.forEach((node) => node.remove());
      nodes.clear();
      if (welcome) welcome.hidden = false;
      setLoading(false);
      newChat.disabled = true;
      input.field.focus();
    }

    newChat.addEventListener("click", reset);
    window.addEventListener(START_CHAT_EVENT, () => {
      if (section.scrollIntoView) section.scrollIntoView({ behavior: "smooth", block: "start" });
      input.field.focus({ preventScroll: true });
    });

    return { ask: ask, retry: retry, reset: reset, state: state };
  }

  A.chat = { setupChat, startChat, historyFrom, linkCitations, formatPhone, START_CHAT_EVENT, PHOTO_QUESTION, CONTACT_QUESTION, ADMISSION_QUESTION };
})((window.Arivazhai = window.Arivazhai || {}));
