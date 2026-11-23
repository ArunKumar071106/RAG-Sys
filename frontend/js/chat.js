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
    assistantMessage: "message--assistant flex w-full max-w-[820px] flex-col items-start gap-2",
    // an answer; exactly one of the looks below goes with it (spacing and colours live in the look, never twice)
    bubble: "bubble w-full min-w-0 text-[1rem] leading-[1.65] wrap-anywhere",
    plain: "py-0.5",
    userBubble: "bubble max-w-[min(620px,85%)] rounded-[20px_20px_6px_20px] bg-navy px-4 py-2.5 whitespace-pre-wrap text-white wrap-anywhere max-phone:max-w-[88%]",
    noAnswer: "rounded-xl border-l-4 border-l-gold bg-cream px-4 py-3",
    errorBubble: "rounded-xl border border-danger bg-danger-bg px-4 py-3",
    loadingBubble: "flex flex-[0_1_auto] items-center gap-2.5 py-1",
    dots: "inline-flex gap-1 [&>span]:size-[7px] [&>span]:animate-dot [&>span]:rounded-full [&>span]:bg-brand [&>span:nth-child(2)]:[animation-delay:0.2s] [&>span:nth-child(3)]:[animation-delay:0.4s] motion-reduce:[&>span]:animate-none motion-reduce:[&>span]:opacity-70",
    muted: "text-[0.9rem] text-muted",
    suggestions: "suggestions mt-3.5",
    followUps: "suggestions mt-1 w-full max-w-[820px]",
    sectionTitle: "mt-0 mb-2 text-[0.9rem] tracking-[0.04em] text-muted uppercase",
    suggestionsTitle: "mt-0 mb-2 text-[0.95rem] tracking-[0.04em] text-muted uppercase",
    chipList: "m-0 flex list-none flex-wrap gap-2 p-0",
    chip: "chip cursor-pointer rounded-2xl border border-line bg-white px-3.5 py-2 text-left text-[0.9rem] text-navy shadow-[0_1px_2px_rgba(13,27,61,0.06)] enabled:hover:border-navy enabled:hover:bg-subtle",
    sources: "sources mt-4 rounded-xl border border-line bg-subtle/60 px-3.5 py-3",
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
    contactList: "m-0 flex list-none flex-wrap gap-x-[18px] gap-y-1.5 p-0 [&>li]:inline-flex [&>li]:items-center [&>li]:gap-1.5 [&_svg]:text-brand [&_a]:font-bold [&_a]:text-navy",
    contactNote: "text-[0.85rem] text-muted",
    contactSubtitle: "mt-2.5 mb-1 text-[0.85rem] text-navy",
    contactPeople: "m-0 grid list-none grid-cols-[repeat(auto-fill,minmax(230px,1fr))] gap-x-[18px] gap-y-1 p-0",
    contactPerson: "flex flex-wrap justify-between gap-x-2.5 gap-y-0.5 [&_a]:font-bold [&_a]:whitespace-nowrap [&_a]:text-navy",
    contactRole: "block text-[0.8rem] text-muted",
    translate: "mt-2.5 flex flex-wrap items-center gap-2",
    translateButton: "translate__button inline-flex items-center gap-1.5 cursor-pointer rounded-full border border-field bg-white px-3.5 py-1.5 text-[0.85rem] font-semibold text-navy enabled:hover:border-navy enabled:hover:bg-navy enabled:hover:text-white aria-pressed:border-navy aria-pressed:bg-navy aria-pressed:text-white",
    translateError: "translate__error text-[0.85rem] text-danger",
    notice: "mt-2.5 mb-0 text-[0.85rem] text-muted italic",
    error: "flex flex-wrap items-center gap-2.5",
    errorIcon: "grid size-6 shrink-0 place-items-center rounded-full bg-danger font-extrabold text-white",
    errorText: "m-0 min-w-[180px] flex-1 text-danger-text",
    retry: "inline-flex min-h-8 cursor-pointer items-center justify-center gap-1.5 rounded-pill border border-brand bg-white px-3.5 py-1 text-[0.85rem] font-medium whitespace-nowrap text-brand enabled:hover:bg-brand enabled:hover:text-white disabled:cursor-not-allowed disabled:opacity-55",
    option: "cursor-pointer px-4 py-[9px] leading-[1.35] text-ink [&_strong]:font-semibold [&_strong]:text-brand",
    // under every answer, like chat apps: copy, listen, thumbs up / down
    feedback: "feedback mt-2 flex flex-wrap items-center gap-1 text-[0.85rem] text-muted",
    action: "action grid size-9 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-muted enabled:hover:bg-subtle enabled:hover:text-navy aria-pressed:text-navy aria-pressed:bg-navy/10 disabled:cursor-default",
    rate: "rate grid size-9 cursor-pointer place-items-center rounded-full border-0 bg-transparent text-muted enabled:hover:bg-subtle enabled:hover:text-navy aria-pressed:bg-navy/10 aria-pressed:text-navy disabled:cursor-default",
    actionNote: "ml-1 text-[0.8rem] text-muted",
    comment: "mt-1 flex w-full flex-wrap items-center gap-2",
    commentField: "min-w-[220px] flex-1 rounded-lg border-2 border-field bg-white px-3 py-1.5 text-[0.9rem] text-ink focus-visible:border-navy",
    smallButton: "cursor-pointer rounded-full border border-navy bg-navy px-3.5 py-1.5 text-[0.85rem] font-semibold text-white hover:bg-navy-dark",
    talk: "talk mt-2.5 flex flex-wrap items-center gap-x-3 gap-y-1.5 text-[0.85rem] text-muted [&_a]:inline-flex [&_a]:items-center [&_a]:gap-1.5 [&_a]:rounded-full [&_a]:border [&_a]:border-field [&_a]:bg-white [&_a]:px-3 [&_a]:py-1 [&_a]:font-semibold [&_a]:text-navy [&_a]:no-underline [&_a:hover]:border-navy",
    optionActive: "bg-subtle",
  };

  // ------------------------------------------------------------------ small helpers
  const ICONS = {
    phone: "M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.6a1 1 0 0 1-.25 1z",
    mail: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 4-8 5-8-5V6l8 5 8-5z",
    chat: "M20 2H4a2 2 0 0 0-2 2v18l4-4h14a2 2 0 0 0 2-2V4a2 2 0 0 0-2-2zM6 9h12v2H6zm8 5H6v-2h8zm4-6H6V6h12z",
    translate: "M12.87 15.07l-2.54-2.51.03-.03A17.5 17.5 0 0 0 14.07 6H17V4h-7V2H8v2H1v2h11.17C11.5 7.92 10.44 9.75 9 11.35 8.07 10.32 7.3 9.19 6.69 8h-2c.73 1.63 1.73 3.17 2.98 4.56l-5.09 5.02L4 19l5-5 3.11 3.11.76-2.04zM18.5 10h-2L12 22h2l1.12-3h4.75L21 22h2l-4.5-12zm-2.62 7l1.62-4.33L19.12 17h-3.24z",
    thumbUp: "M1 21h4V9H1v12zm22-11a2 2 0 0 0-2-2h-6.31l.95-4.57.03-.32c0-.41-.17-.79-.44-1.06L14.17 1 7.59 7.59C7.22 7.95 7 8.45 7 9v10a2 2 0 0 0 2 2h9c.83 0 1.54-.5 1.84-1.22l3.02-7.05c.09-.23.14-.47.14-.73v-2z",
    copy: "M16 1H4a2 2 0 0 0-2 2v14h2V3h12V1zm3 4H8a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h11a2 2 0 0 0 2-2V7a2 2 0 0 0-2-2zm0 16H8V7h11v14z",
    check: "M9 16.17 4.83 12l-1.42 1.41L9 19 21 7l-1.41-1.41z",
    volume: "M3 9v6h4l5 5V4L7 9H3zm13.5 3A4.5 4.5 0 0 0 14 7.97v8.05c1.48-.73 2.5-2.25 2.5-4.02zM14 3.23v2.06a7 7 0 0 1 0 13.42v2.06A9 9 0 0 0 14 3.23z",
    stop: "M6 6h12v12H6z",
    thumbDown: "M15 3H6c-.83 0-1.54.5-1.84 1.22l-3.02 7.05c-.09.23-.14.47-.14.73v2a2 2 0 0 0 2 2h6.31l-.95 4.57-.03.32c0 .41.17.79.44 1.06L9.83 23l6.59-6.59c.36-.36.58-.86.58-1.41V5a2 2 0 0 0-2-2zm4 0v12h4V3h-4z",
  };

  /** A small icon in the colour of the text around it (decorative: the words beside it say what it is). */
  function icon(name, size) {
    const ns = "http://www.w3.org/2000/svg";
    const svg = document.createElementNS(ns, "svg");
    svg.setAttribute("viewBox", "0 0 24 24");
    svg.setAttribute("width", String(size || 16));
    svg.setAttribute("height", String(size || 16));
    svg.setAttribute("aria-hidden", "true");
    svg.setAttribute("focusable", "false");
    svg.setAttribute("class", "icon inline-block shrink-0");
    const path = document.createElementNS(ns, "path");
    path.setAttribute("fill", "currentColor");
    path.setAttribute("d", ICONS[name]);
    svg.append(path);
    return svg;
  }

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
  /** Answers the admission office wrote are pages of our own backend (/api/answers/<id>), not of the website. */
  const OFFICE_ANSWER = "/api/answers/";
  function sourceUrl(url) {
    const value = String(url || "");
    if (!value.startsWith(OFFICE_ANSWER)) return value;
    try {
      return new URL(A.api.apiUrl(value), window.location.href).toString();
    } catch (e) {
      return value;
    }
  }

  function linkCitations(answer, sources, images, prefix) {
    const byId = new Map(sources.map((s) => [s.id, s]));
    const imageIds = new Set(images.map((i) => i.id));
    return answer.replace(/\[(S|I)(\d+)\]/g, (match, kind, num) => {
      if (kind === "S") {
        const source = byId.get("S" + num);
        return source ? "[[" + num + "]](" + sourceUrl(source.url) + ' "Source ' + num + ": " + escapeTitle(source.title) + '")' : "";
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
          const href = safeHref(sourceUrl(source.url));
          const office = String(source.url || "").startsWith(OFFICE_ANSWER);
          const label = href
            ? el("a", { href: href, target: "_blank", rel: "noopener noreferrer", class: C.sourceLink }, [
                source.title,
                office ? el("span", { class: C.sourceHeading, text: " - " + t("fromOffice") })
                  : source.heading ? el("span", { class: C.sourceHeading, text: " - " + source.heading }) : null,
                hidden(" (opens in a new tab)"),
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
          icon("phone"),
          el("a", { href: telHref(phone), text: formatPhone(phone) }),
          /^1800/.test(phone.replace(/\D/g, "")) ? el("span", { class: C.contactNote, text: " " + t("tollFree") }) : null,
        ]),
      );
    }
    for (const email of site.emails) {
      items.push(el("li", null, [icon("mail"), el("a", { href: "mailto:" + email, text: email })]));
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
      button.append(icon("translate"), words);
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

  /** Reading an answer aloud (the browser's own voices; English or Tamil by the answer's letters). */
  const speech = window.speechSynthesis && typeof window.SpeechSynthesisUtterance === "function" ? window.speechSynthesis : null;
  let speaking = null; // the Listen button of the answer being read

  function speakingDone() {
    if (!speaking) return;
    speaking.setAttribute("aria-pressed", "false");
    speaking.setAttribute("aria-label", t("listen"));
    speaking.title = t("listen");
    speaking.replaceChildren(icon("volume", 18));
    speaking = null;
  }

  /**
   * Under every answer, as in chat apps: Copy, Listen, and thumbs up / down ("Was this answer
   * helpful?"); thumbs down asks what was wrong (optional), then both are sent together.
   */
  function feedbackBar(question, answer, textOf) {
    const note = el("span", { class: C.actionNote, "aria-live": "polite" });
    const say = (words) => {
      note.textContent = words;
      clearTimeout(note.timer);
      note.timer = setTimeout(() => (note.textContent = ""), 2500);
    };
    const plainText = () => String(textOf ? textOf() : answer).replace(/\[(\d+|image \d+)\]/g, "").replace(/\s+\n/g, "\n").trim();

    const copy = el("button", { type: "button", class: C.action, "aria-label": t("copy"), title: t("copy") }, [icon("copy", 18)]);
    copy.addEventListener("click", async () => {
      try {
        await navigator.clipboard.writeText(plainText());
        copy.replaceChildren(icon("check", 18));
        say(t("copied"));
        setTimeout(() => copy.replaceChildren(icon("copy", 18)), 2000);
      } catch (e) {
        /* no clipboard (an old browser, or not allowed): nothing to do */
      }
    });

    let listen = null;
    if (speech) {
      listen = el("button", { type: "button", class: C.action, "aria-pressed": "false", "aria-label": t("listen"), title: t("listen") }, [icon("volume", 18)]);
      listen.addEventListener("click", () => {
        const mine = speaking === listen;
        speech.cancel();
        speakingDone();
        if (mine) return; // a second press stops it
        const text = plainText();
        const utterance = new window.SpeechSynthesisUtterance(text);
        utterance.lang = /[\u0B80-\u0BFF]/.test(text) ? "ta-IN" : "en-IN";
        utterance.onend = utterance.onerror = () => {
          if (speaking === listen) speakingDone();
        };
        speaking = listen;
        listen.setAttribute("aria-pressed", "true");
        listen.setAttribute("aria-label", t("stopListen"));
        listen.title = t("stopListen");
        listen.replaceChildren(icon("stop", 18));
        speech.speak(utterance);
      });
    }

    const up = el("button", { type: "button", class: C.rate, "aria-pressed": "false", "aria-label": t("yes"), title: t("yes") }, [icon("thumbUp", 18)]);
    const down = el("button", { type: "button", class: C.rate, "aria-pressed": "false", "aria-label": t("no"), title: t("no") }, [icon("thumbDown", 18)]);
    const box = el("div", { class: C.feedback }, [copy, listen, hidden(t("helpful")), up, down, note]);
    const thanks = () => {
      note.textContent = t("thanks");
    };
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
        form.remove();
        thanks();
      });
      box.append(form);
      field.focus();
    });
    return box;
  }

  /** "Need to talk to someone?": call, email and (when the office gives a number) WhatsApp, under every answer. */
  function talkBar() {
    const phone = site.officePhones[0];
    const email = site.emails.find((e) => /admission/i.test(e)) || site.emails[0];
    const links = [
      phone ? el("a", { href: telHref(phone) }, [icon("phone"), t("call")]) : null,
      email ? el("a", { href: "mailto:" + email }, [icon("mail"), t("email")]) : null,
      site.whatsapp
        ? el("a", { href: "https://wa.me/" + String(site.whatsapp).replace(/\D/g, ""), target: "_blank", rel: "noopener noreferrer" },
            [icon("chat"), t("whatsapp")])
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
        feedbackBar(question, message.content, () => markdown.textContent),
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

    function grow() {
      field.style.height = "auto";
      if (field.scrollHeight) field.style.height = Math.min(field.scrollHeight, 160) + "px";
    }

    function refresh() {
      grow();
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
        if (status) {
          status.textContent = t(key);
          status.setAttribute("data-state", key);
        }
      };
      let checks = [];
      const stop = () => {
        recognition = null;
        checks.forEach(clearTimeout);
        checks = [];
        mic.setAttribute("aria-pressed", "false");
        mic.setAttribute("aria-label", t("mic"));
      };
      /** Arivazhai says when the voice is not audible: nothing heard, only noise, or no microphone. */
      const cantHear = (kind) => {
        say("hint");
        if (A.robot && A.robot.moments) A.robot.moments.show({ kind: "unsure", title: t("m_" + kind + "_title"), text: t("m_" + kind + "_text") });
        if (status) {
          status.textContent = t("m_" + kind + "_title") + ". " + t("m_" + kind + "_text");
          status.setAttribute("data-state", "voice");
        }
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
        // what the microphone has picked up so far: any sound at all, and a voice in it
        const ear = { sound: false, speech: false, words: false };
        const current = recognition;
        recognition.onsoundstart = () => (ear.sound = true);
        recognition.onspeechstart = () => {
          ear.sound = ear.speech = true;
          say("hearing");
        };
        recognition.onaudiostart = () => {
          // no sound at all for 4 s: too quiet (or the microphone is muted)
          checks.push(setTimeout(() => {
            if (recognition === current && !ear.sound) {
              cantHear("quiet");
              current.abort();
            }
          }, 4000));
          // sound but no words for 7 s: too much noise, or too far away
          checks.push(setTimeout(() => {
            if (recognition === current && !ear.words) {
              cantHear(ear.speech || ear.sound ? "noisy" : "quiet");
              current.abort();
            }
          }, 7000));
        };
        recognition.onresult = (event) => {
          ear.words = true;
          const heard = Array.from(event.results).map((r) => r[0].transcript).join(" ").trim();
          field.value = (before ? before + " " : "") + heard;
          typed = false; // no type-ahead list over spoken words
          refresh();
        };
        recognition.onerror = (event) => {
          if (event.error === "aborted") return; // stopped by the checks above, which already said why
          if (event.error === "no-speech") cantHear(ear.sound ? "noisy" : "quiet");
          else if (event.error === "audio-capture") cantHear("nomic");
          else say(event.error === "not-allowed" || event.error === "service-not-allowed" ? "micDenied" : "micFailed");
          stop();
        };
        recognition.onend = () => {
          if (status && (status.textContent === t("listening") || status.textContent === t("hearing"))) say("hint");
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

  const phoneApp = () => !!(window.matchMedia && window.matchMedia("(max-width: 760px)").matches);

  function showMoment(event) {
    if (event.type === "retrieving") {
      if (!phoneApp()) robot.moments.show({ kind: "think" }); // phones: "Searching…" with the robot, inline
    } else if (event.type === "failed") robot.moments.show(robot.momentForFailure(event.kind));
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
    // who is chatting (js/user.js): the sign-in form shows until a name and mobile number are given
    const people = opts.people !== undefined ? opts.people : A.user || null;
    const dialog = section.querySelector(".confirm-new");

    if (welcome) {
      welcome.querySelectorAll(".chip").forEach((chip) => {
        chip.setAttribute("data-busy", "");
        chip.addEventListener("click", () => ask(chip.textContent.trim()));
      });
    }

    /** The question and "searching" stay in sight at the bottom; a new answer is shown from its first line. */
    function scrollToEnd() {
      const last = log.lastElementChild;
      if (!last || !last.scrollIntoView) return;
      const latest = state.messages[state.messages.length - 1];
      const isAnswer = !state.loading && latest && latest.role === "assistant" && nodes.get(latest.id) === last;
      last.scrollIntoView({ block: isAnswer ? "start" : "end", behavior: "smooth" });
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
      remember();
    }

    /** The conversation, saved in this browser for this person (errors are not kept). */
    function remember() {
      if (!people) return;
      people.history.save(state.messages.map((m) => ({ id: m.id, role: m.role, content: m.content, result: m.result,
                                                       question: m.question, error: m.error })));
    }

    /** After a reload (or signing in again on this device): the saved conversation comes back. */
    function restore() {
      if (!people || !people.current()) return;
      people.history.load().forEach((m) => {
        if (m && (m.role === "user" || (m.role === "assistant" && m.result))) add({ ...m, id: m.id || nextId() });
      });
      drawFollowUps();
      newChat.disabled = state.messages.length === 0;
      log.scrollTop = log.scrollHeight; // phones: the conversation opens at its latest message
    }

    /** Clear the screen (not the saved history): another person signs in, or one signs out. */
    function clearScreen() {
      if (state.controller) state.controller.abort();
      state.controller = null;
      state.messages = [];
      nodes.forEach((node) => node.remove());
      nodes.clear();
      if (welcome) welcome.hidden = false;
      setLoading(false);
      newChat.disabled = true;
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
        if (err instanceof api.ApiError && err.kind === "login" && people) {
          people.signOut(); // the server no longer knows this visitor: ask for the name and number again
          return;
        }
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

    /** New chat: the conversation is deleted from the screen and from this device. */
    function reset() {
      clearScreen();
      if (people) people.history.clear();
      input.field.focus();
    }

    /** "New chat" asks first, because the saved conversation is deleted for good. */
    function confirmNewChat() {
      if (!state.messages.length) return Promise.resolve(true);
      if (!dialog || typeof dialog.showModal !== "function") {
        return Promise.resolve(window.confirm(t("newChatTitle") + "\n\n" + t("newChatText")));
      }
      return new Promise((resolve) => {
        dialog.returnValue = "";
        dialog.addEventListener("close", () => resolve(dialog.returnValue === "confirm"), { once: true });
        dialog.showModal();
        const keep = dialog.querySelector('button[value="cancel"]');
        if (keep) keep.focus(); // the safe choice has the focus
      });
    }

    newChat.addEventListener("click", () => {
      confirmNewChat().then((ok) => {
        if (ok) reset();
      });
    });
    window.addEventListener(START_CHAT_EVENT, () => {
      if (section.scrollIntoView) section.scrollIntoView({ behavior: "smooth", block: "start" });
      const first = section.classList.contains("is-signed-out") ? section.querySelector("#login-name") : input.field;
      if (first) first.focus({ preventScroll: true });
    });

    setupSignIn();
    setupJump();

    /** Phones (the conversation scrolls in its own box): a round arrow back to the latest message. */
    function setupJump() {
      const jump = section.querySelector(".chat__jump");
      if (!jump) return;
      const update = () => {
        const scrolls = log.scrollHeight > log.clientHeight + 4;
        jump.hidden = !scrolls || log.scrollHeight - log.scrollTop - log.clientHeight < 240;
      };
      log.addEventListener("scroll", update, { passive: true });
      jump.addEventListener("click", () => {
        log.scrollTo({ top: log.scrollHeight, behavior: "smooth" });
        input.field.focus({ preventScroll: true });
      });
    }

    /** The sign-in form (name + mobile number) and "Not you?". */
    function setupSignIn() {
      const form = section.querySelector(".chat-login");
      const name = section.querySelector(".chat__name");
      const hello = section.querySelector(".welcome__name");
      const show = (user) => {
        section.classList.toggle("is-signed-out", !user);
        if (name) name.textContent = user ? user.name : "";
        if (hello) hello.textContent = user && user.name ? ", " + user.name : ""; // "Hello, Meena"
      };
      if (!people) {
        show({ name: "" }); // a page without sign-in (tests, or LOGIN_REQUIRED switched off)
        return;
      }
      show(people.current());
      restore();
      people.onChange((user) => {
        clearScreen();
        show(user);
        if (user) restore();
      });
      const signOut = section.querySelector(".chat__signout");
      if (signOut) signOut.addEventListener("click", () => {
        people.signOut();
        const first = section.querySelector("#login-name");
        if (first) first.focus();
      });
      if (!form) return;
      const nameField = form.querySelector("#login-name");
      const phoneField = form.querySelector("#login-phone");
      const button = form.querySelector(".chat-login__submit");
      const status = form.querySelector(".chat-login__status");
      const showError = (field, id, message) => {
        const box = form.querySelector("#" + id);
        field.setAttribute("aria-invalid", message ? "true" : "false");
        if (box) {
          box.textContent = message || "";
          box.hidden = !message;
        }
      };
      form.addEventListener("submit", async (event) => {
        event.preventDefault();
        const checked = people.validate(nameField.value, phoneField.value);
        showError(nameField, "login-name-error", checked.errors.name);
        showError(phoneField, "login-phone-error", checked.errors.phone);
        status.textContent = "";
        if (checked.errors.name || checked.errors.phone) {
          (checked.errors.name ? nameField : phoneField).focus();
          return;
        }
        button.disabled = true;
        button.textContent = t("loginBusy");
        try {
          await people.signIn(checked.name, checked.phone);
          phoneField.value = "";
          input.field.focus();
        } catch (err) {
          status.textContent = (err && err.message) || t("loginFailed");
        } finally {
          button.disabled = false;
          button.textContent = t("loginButton");
        }
      });
    }

    return { ask: ask, retry: retry, reset: reset, state: state };
  }

  A.chat = { setupChat, startChat, historyFrom, linkCitations, formatPhone, START_CHAT_EVENT, PHOTO_QUESTION, CONTACT_QUESTION, ADMISSION_QUESTION };
})((window.Arivazhai = window.Arivazhai || {}));
