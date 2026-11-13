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
  const t = (key) => A.i18n.t(key);

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


  /**
   * Tailwind classes of the elements the chat creates (css/tailwind.input.css has the theme:
   * brand, navy, gold, line, field, muted ...). A plain name first (message--user, chip, markdown)
   * is a hook for the scripts and tests, not a style.
   */
  const C = {
    sender: "inline-flex items-center gap-2 text-[0.72rem] font-extrabold tracking-[0.04em] text-gold-text uppercase",
    profileSmall: "profile grid size-[26px] shrink-0 place-items-center overflow-hidden rounded-full border-[1.5px] border-gold bg-navy-dark",
    userMessage: "message--user flex items-start justify-end gap-2.5",
    assistantMessage: "message--assistant flex flex-col items-start gap-1.5",
    // an answer bubble; one of the colour sets below goes with it (two colour classes on one element would clash)
    bubble: "bubble w-[min(880px,100%)] max-w-[min(780px,100%)] min-w-0 rounded-[4px_16px_16px_16px] border px-4 py-3 wrap-anywhere",
    plain: "border-line bg-white",
    userBubble: "bubble max-w-[min(620px,85%)] rounded-[16px_4px_16px_16px] bg-navy px-4 py-3 whitespace-pre-wrap text-white wrap-anywhere max-phone:max-w-[90%]",
    noAnswer: "border-y-line border-r-line border-l-4 border-l-gold bg-white",
    errorBubble: "border-danger bg-danger-bg",
    loadingBubble: "flex flex-[0_1_auto] items-center gap-2.5",
    dots: "inline-flex gap-1 [&>span]:size-[7px] [&>span]:animate-dot [&>span]:rounded-full [&>span]:bg-brand [&>span:nth-child(2)]:[animation-delay:0.2s] [&>span:nth-child(3)]:[animation-delay:0.4s] motion-reduce:[&>span]:animate-none motion-reduce:[&>span]:opacity-70",
    muted: "text-[0.9rem] text-muted",
    suggestions: "suggestions mt-3.5",
    followUps: "suggestions mt-1 w-[min(880px,100%)]",
    sectionTitle: "mt-0 mb-2 text-[0.9rem] tracking-[0.04em] text-muted uppercase",
    suggestionsTitle: "mt-0 mb-2 text-[0.95rem] tracking-[0.04em] text-muted uppercase",
    chipList: "m-0 flex list-none flex-wrap gap-2 p-0",
    chip: "chip cursor-pointer rounded-full border border-field bg-white px-4 py-2 text-left text-[0.9rem] text-navy enabled:hover:border-navy enabled:hover:bg-navy enabled:hover:text-white",
    sources: "sources mt-3.5 border-t border-edge pt-3",
    sourceList: "m-0 grid list-none gap-2 p-0",
    sourceItem: "flex gap-2.5",
    sourceNum: "mt-0.5 grid size-[22px] shrink-0 place-items-center rounded-full bg-brand text-[0.75rem] font-bold text-white",
    sourceLink: "font-semibold",
    sourceHeading: "font-normal text-muted",
    sourceSnippet: "mt-0.5 mb-0 text-[0.85rem] text-muted",
    images: "images mt-3.5",
    imageGrid: "grid grid-cols-[repeat(auto-fill,minmax(210px,1fr))] gap-3",
    imageCard: "image-card m-0 flex flex-col overflow-hidden rounded-brand border border-edge bg-white",
    imageFrame: "relative aspect-[4/3] max-h-[260px] w-full bg-subtle",
    // contain, not cover: posters and notices must never be cropped
    image: "block size-full object-contain",
    imageMissing: "flex h-full min-h-[120px] flex-col items-center justify-center gap-1.5 text-[0.85rem] text-muted",
    imageBadge: "absolute right-2 bottom-2 rounded-full bg-black/70 px-2 py-0.5 text-[0.72rem] text-white",
    imageCaption: "flex flex-col gap-1 px-3 pt-2.5 pb-3 text-[0.85rem]",
    imageTitle: "font-semibold",
    imageMeta: "text-muted",
    imageSummary: "cursor-pointer text-link",
    imageOcr: "mt-1.5 mb-0 font-mono text-[0.8rem] whitespace-pre-wrap",
    imageAi: "m-0 text-muted",
    aiTag: "tag--ai inline-block rounded-[3px] border border-ai-line bg-ai-bg px-1.5 py-px text-[0.7rem] font-bold tracking-[0.03em] text-ai-text uppercase",
    imageLinks: "mt-0.5 flex flex-wrap gap-x-3.5 gap-y-1",
    contactCard: "contact-card mt-3.5 rounded-[10px] border border-l-4 border-line border-l-gold bg-cream px-3.5 py-3",
    contactTitle: "mt-0 mb-1.5 text-[0.9rem] text-navy",
    contactList: "m-0 flex list-none flex-wrap gap-x-[18px] gap-y-1.5 p-0 [&_a]:font-bold [&_a]:text-navy",
    contactNote: "text-[0.85rem] text-muted",
    contactSubtitle: "mt-2.5 mb-1 text-[0.85rem] text-navy",
    contactPeople: "m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-x-[18px] gap-y-1 p-0",
    contactPerson: "flex flex-wrap justify-between gap-x-2.5 gap-y-0.5 [&_a]:font-bold [&_a]:whitespace-nowrap [&_a]:text-navy",
    contactRole: "block text-[0.8rem] text-muted",
    translate: "mt-2.5 flex flex-wrap items-center gap-2",
    translateButton: "translate__button cursor-pointer rounded-full border border-field bg-white px-3.5 py-1.5 text-[0.85rem] font-semibold text-navy enabled:hover:border-navy enabled:hover:bg-navy enabled:hover:text-white aria-pressed:border-navy aria-pressed:bg-navy aria-pressed:text-white",
    translateError: "translate__error text-[0.85rem] text-danger",
    notice: "mt-2.5 mb-0 text-[0.85rem] text-muted italic",
    error: "flex flex-wrap items-center gap-2.5",
    errorIcon: "grid size-6 shrink-0 place-items-center rounded-full bg-danger font-extrabold text-white",
    errorText: "m-0 min-w-[180px] flex-1 text-danger-text",
    retry: "inline-flex min-h-8 cursor-pointer items-center justify-center gap-1.5 rounded-pill border border-brand bg-white px-3.5 py-1 text-[0.85rem] font-medium whitespace-nowrap text-brand enabled:hover:bg-brand enabled:hover:text-white disabled:cursor-not-allowed disabled:opacity-55",
    option: "cursor-pointer px-4 py-[9px] leading-[1.35] text-ink [&_strong]:font-semibold [&_strong]:text-brand",
    feedback: "feedback mt-3 flex flex-wrap items-center gap-2 border-t border-line pt-2.5 text-[0.85rem] text-muted",
    rate: "rate grid size-9 cursor-pointer place-items-center rounded-full border border-field bg-white text-[1.05rem] enabled:hover:border-navy aria-pressed:border-navy aria-pressed:bg-navy/10 disabled:cursor-default",
    comment: "mt-1 flex w-full flex-wrap items-center gap-2",
    commentField: "min-w-[220px] flex-1 rounded-lg border-2 border-field bg-white px-3 py-1.5 text-[0.9rem] text-ink focus-visible:border-navy",
    smallButton: "cursor-pointer rounded-full border border-navy bg-navy px-3.5 py-1.5 text-[0.85rem] font-semibold text-white hover:bg-navy-dark",
    talk: "talk mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[0.85rem] text-muted [&_a]:inline-flex [&_a]:items-center [&_a]:gap-1 [&_a]:rounded-full [&_a]:border [&_a]:border-field [&_a]:bg-white [&_a]:px-3 [&_a]:py-1 [&_a]:font-semibold [&_a]:text-navy [&_a]:no-underline [&_a:hover]:border-navy",
    optionActive: "bg-subtle",
  };

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
  const hidden = (text) => el("span", { class: "sr-only", text: text });

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
    const profile = el("span", { class: C.profileSmall, "data-robot": "head" });
    robot.drawProfiles(el("div", null, [profile]));
    return el("span", { class: C.sender, "aria-hidden": "true" }, [profile, "Arivazhai"]);
  }

  /** Clickable questions: the welcome's "Try asking" and the "You can also ask" under an answer. */
  function suggestionList(questions, title, onSelect, classes) {
    const titleId = nextId();
    return el("div", { class: classes || C.suggestions }, [
      el("h3", { class: C.suggestionsTitle, id: titleId, text: title }),
      el(
        "ul",
        { class: C.chipList, "aria-labelledby": titleId },
        questions.map((q) => el("li", null, [el("button", { type: "button", class: C.chip, "data-busy": true, text: q, onclick: () => onSelect(q) })])),
      ),
    ]);
  }

  function sourceList(sources, title, variant) {
    if (!sources.length) return null;
    return el("section", { class: C.sources, "aria-label": title }, [
      el("h4", { class: C.sectionTitle, text: title }),
      el(
        "ol",
        { class: C.sourceList },
        sources.map((source, index) => {
          const href = safeHref(source.url);
          const label = href
            ? el("a", { href: href, target: "_blank", rel: "noopener noreferrer", class: C.sourceLink }, [
                source.title,
                source.heading ? el("span", { class: C.sourceHeading, text: " - " + source.heading }) : null,
                hidden(" (opens official page in a new tab)"),
              ])
            : el("span", { class: C.sourceLink, text: source.title });
          return el("li", { class: C.sourceItem }, [
            variant === "cited" ? el("span", { class: C.sourceNum, "aria-hidden": "true", text: String(index + 1) }) : null,
            el("div", null, [label, source.snippet ? el("p", { class: C.sourceSnippet, text: source.snippet }) : null]),
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

    const frame = el("div", { class: C.imageFrame });
    if (image.width && image.height) frame.style.aspectRatio = image.width + " / " + image.height;
    const img = el("img", { class: C.image, src: api.apiUrl(image.src), alt: alt, loading: "lazy", decoding: "async" });
    let triedOriginal = false;
    img.addEventListener("error", () => {
      if (!triedOriginal && originalHref) {
        triedOriginal = true;
        img.src = originalHref;
        return;
      }
      const missing = el("div", { class: C.imageMissing, role: "img", "aria-label": "Image unavailable: " + alt }, [el("span", { text: "Image unavailable" })]);
      missing.insertAdjacentHTML(
        "afterbegin",
        '<svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" focusable="false"><path fill="currentColor" d="M21 5v14H3V5h18m0-2H3a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h18a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm-7.5 9.5-3 3.9-2-2.6L5.5 17h13l-5-4.5z"/></svg>',
      );
      img.replaceWith(missing);
    });
    frame.append(img, el("span", { class: C.imageBadge, text: "Image " + index }));

    const links = el("span", { class: C.imageLinks }, [
      pageHref ? el("a", { href: pageHref, target: "_blank", rel: "noopener noreferrer" }, ["View source page", hidden(" (opens in a new tab)")]) : null,
      originalHref ? el("a", { href: originalHref, target: "_blank", rel: "noopener noreferrer" }, ["Open image", hidden(" (opens in a new tab)")]) : null,
    ]);
    const caption = el("figcaption", { class: C.imageCaption }, [
      el("span", { class: C.imageTitle, text: title }),
      meta ? el("span", { class: C.imageMeta, text: meta }) : null,
      image.ocr_text
        ? el("details", null, [el("summary", { class: C.imageSummary, text: "Text in image (OCR)" }), el("p", { class: C.imageOcr, text: image.ocr_text })])
        : null,
      image.description_is_ai_generated && image.description
        ? el("p", { class: C.imageAi }, [el("span", { class: C.aiTag, text: "AI-generated description" }), " " + image.description])
        : null,
      links,
    ]);
    return el("figure", { class: C.imageCard, id: anchorId }, [frame, caption]);
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
          /^1800/.test(phone.replace(/\D/g, "")) ? el("span", { class: C.contactNote, text: " " + t("tollFree") }) : null,
        ]),
      );
    }
    for (const email of site.emails) {
      items.push(el("li", null, [el("span", { "aria-hidden": "true", text: "✉️" }), " ", el("a", { href: "mailto:" + email, text: email })]));
    }
    const card = el("section", { class: C.contactCard, "aria-label": title }, [el("h4", { class: C.contactTitle, text: title }), el("ul", { class: C.contactList }, items)]);
    if (staff && site.admissionStaff.length) {
      card.append(
        el("h5", { class: C.contactSubtitle, text: t("staffTitle") }),
        el(
          "ul",
          { class: C.contactPeople },
          site.admissionStaff.map((person) =>
            el("li", { class: C.contactPerson }, [
              el("span", null, [person.name, person.role ? el("span", { class: C.contactRole, text: person.role }) : null]),
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
    const button = el("button", { type: "button", class: C.translateButton, "aria-pressed": "false" });
    const label = (words) => {
      button.textContent = "";
      button.append(el("span", { "aria-hidden": "true", text: "🌐" }), " " + words);
    };
    label(t("showEnglish"));
    const box = el("div", { class: C.translate }, [button]);
    button.addEventListener("click", async () => {
      const error = box.querySelector(".translate__error");
      if (error) error.remove();
      if (showing || english) {
        showing = !showing;
        show(showing ? english : null);
        button.setAttribute("aria-pressed", String(showing));
        label(showing ? t("showOriginal") : t("showEnglish"));
        return;
      }
      button.disabled = true;
      label(t("translating"));
      try {
        english = await api.translateAnswer(text);
        showing = true;
        show(english);
        button.setAttribute("aria-pressed", "true");
        label(t("showOriginal"));
      } catch (err) {
        label(t("showEnglish"));
        box.append(el("span", { class: C.translateError, role: "alert", text: err instanceof api.ApiError ? err.message : "The English version is not available right now." }));
      } finally {
        button.disabled = false;
      }
    });
    return box;
  }

  /** "Was this answer helpful? 👍 👎": a 👎 asks what was wrong (optional), then both are sent together. */
  function feedbackBar(question, answer) {
    const box = el("div", { class: C.feedback }, [el("span", { text: t("helpful") })]);
    const thanks = () => {
      box.textContent = "";
      box.append(el("span", { role: "status", text: t("thanks") }));
    };
    const up = el("button", { type: "button", class: C.rate, "aria-pressed": "false", "aria-label": t("yes"), title: t("yes"), text: "👍" });
    const down = el("button", { type: "button", class: C.rate, "aria-pressed": "false", "aria-label": t("no"), title: t("no"), text: "👎" });
    up.addEventListener("click", () => {
      up.setAttribute("aria-pressed", "true");
      up.disabled = down.disabled = true;
      api.sendFeedback(question, answer, "up", "");
      setTimeout(thanks, 400);
    });
    down.addEventListener("click", () => {
      down.setAttribute("aria-pressed", "true");
      up.disabled = down.disabled = true;
      const field = el("input", { type: "text", class: C.commentField, maxlength: "500", "aria-label": t("whatWrong"), placeholder: t("whatWrong") });
      const form = el("form", { class: C.comment }, [field, el("button", { type: "submit", class: C.smallButton, text: t("sendFeedback") })]);
      form.addEventListener("submit", (event) => {
        event.preventDefault();
        api.sendFeedback(question, answer, "down", field.value.trim());
        thanks();
      });
      box.append(form);
      field.focus();
    });
    box.append(up, down);
    return box;
  }

  /** "Need to talk to someone?": call, email and (when the office gives a number) WhatsApp, under every answer. */
  function talkBar() {
    const phone = site.officePhones[0];
    const email = site.emails.find((e) => /admission/i.test(e)) || site.emails[0];
    const links = [
      phone ? el("a", { href: telHref(phone) }, [el("span", { "aria-hidden": "true", text: "📞" }), t("call")]) : null,
      email ? el("a", { href: "mailto:" + email }, [el("span", { "aria-hidden": "true", text: "✉️" }), t("email")]) : null,
      site.whatsapp
        ? el("a", { href: "https://wa.me/" + String(site.whatsapp).replace(/\D/g, ""), target: "_blank", rel: "noopener noreferrer" },
            [el("span", { "aria-hidden": "true", text: "💬" }), t("whatsapp")])
        : null,
    ].filter(Boolean);
    return links.length ? el("div", { class: C.talk }, [el("span", { text: t("talk") }), ...links]) : null;
  }

  // ------------------------------------------------------------------ messages
  function renderUser(message) {
    return el("div", { class: C.userMessage }, [
      el("div", { class: C.userBubble }, [hidden("You said: "), el("span", { dir: "auto", text: message.content })]),
    ]);
  }

  function renderError(message, onRetry) {
    const retry = el("button", { type: "button", class: C.retry, "data-busy": true, text: t("tryAgain"), onclick: () => onRetry(message.id) });
    return el("div", { class: C.assistantMessage }, [
      sender(),
      el("div", { class: C.bubble + " " + C.errorBubble }, [
        el("div", { class: C.error, role: "alert" }, [
          el("span", { class: C.errorIcon, "aria-hidden": "true", text: "!" }),
          el("p", { class: C.errorText, text: message.error.message }),
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
      ? el("section", { class: C.images, "aria-label": "Related images from the official website" }, [
          el("h4", { class: C.sectionTitle, text: t("images") }),
          el("div", { class: C.imageGrid }, images.map((image, i) => imageCard(image, i + 1, message.id + "-" + image.id))),
        ])
      : null;
    // "not on the website" and contact questions end with how to reach the college
    const showContact = noAnswer || CONTACT_QUESTION.test(question);
    const showStaff = noAnswer || ADMISSION_QUESTION.test(question);
    const related = result.related_sources || [];

    return el("div", { class: C.assistantMessage }, [
      sender(),
      el("div", { class: C.bubble + " " + (noAnswer ? C.noAnswer : C.plain) }, [
        hidden("Assistant: "),
        photoQuestion ? gallery : null,
        markdown,
        result.translatable ? translateToggle(message.content, showText) : null,
        result.notice ? el("p", { class: C.notice, text: result.notice }) : null,
        photoQuestion ? null : gallery,
        sourceList(sources, t("sources"), "cited"),
        noAnswer && related.length ? sourceList(related, t("related"), "related") : null,
        showContact ? contactCard(noAnswer ? t("officeHelps") : t("contactCollege"), showStaff) : talkBar(),
        feedbackBar(question, message.content),
      ]),
    ]);
  }

  function renderLoading() {
    return el("div", { class: C.assistantMessage, role: "status", "aria-live": "polite" }, [
      sender(),
      el("div", { class: C.bubble + " " + C.plain + " " + C.loadingBubble }, [
        el("span", { class: C.dots, "aria-hidden": "true" }, [el("span"), el("span"), el("span")]),
        el("span", { class: C.muted, text: t("searching") }),
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
    const mic = form.querySelector(".chat-input__mic");
    const status = form.querySelector(".chat-input__status");
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
        const item = el("li", { id: list.id + "-" + i, role: "option", "aria-selected": String(i === active), class: C.option + (i === active ? " is-active " + C.optionActive : "") }, highlighted(s, field.value));
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
    setupVoice();

    /** Ask by voice: the browser turns speech into text in the box (English or Tamil, as the chat's language). */
    function setupVoice() {
      const Recognition = window.SpeechRecognition || window.webkitSpeechRecognition;
      if (!mic || !Recognition) return; // Firefox and some browsers: no voice, the button stays hidden
      mic.hidden = false;
      let recognition = null;
      const say = (key) => {
        if (status) status.textContent = t(key);
      };
      const stop = () => {
        recognition = null;
        mic.setAttribute("aria-pressed", "false");
        mic.setAttribute("aria-label", t("mic"));
      };
      mic.addEventListener("click", () => {
        if (recognition) {
          recognition.stop();
          return;
        }
        recognition = new Recognition();
        recognition.lang = A.i18n.speech;
        recognition.interimResults = true;
        recognition.maxAlternatives = 1;
        const before = field.value.trim();
        recognition.onresult = (event) => {
          const heard = Array.from(event.results).map((r) => r[0].transcript).join(" ").trim();
          field.value = (before ? before + " " : "") + heard;
          typed = false; // no type-ahead list over spoken words
          refresh();
        };
        recognition.onerror = (event) => {
          say(event.error === "not-allowed" || event.error === "service-not-allowed" ? "micDenied" : "micFailed");
          stop();
        };
        recognition.onend = () => {
          if (status && status.textContent === t("listening")) say("hint");
          stop();
          field.focus();
        };
        mic.setAttribute("aria-pressed", "true");
        mic.setAttribute("aria-label", t("micStop"));
        say("listening");
        try {
          recognition.start();
        } catch (e) {
          say("micFailed");
          stop();
        }
      });
    }

    return {
      field: field,
      setDisabled(value) {
        disabled = value;
        if (mic) mic.disabled = value;
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
      followUps = suggestionList(questions, t("alsoAsk"), ask, C.followUps);
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
