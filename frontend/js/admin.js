/*
 * The admin panel (admin.html): sign in with the admin password (ADMIN_TOKEN), then
 *   Dashboard            frequent questions, when people ask (hour, weekday, day), answer times, ratings
 *   Unanswered questions answer them: the answer is chunked and indexed like a website page
 *   Your answers         edit or delete them
 *   Visitors             download the Excel file of names and mobile numbers
 * The password is kept for this browser tab only (sessionStorage). Everything is built with DOM
 * methods, never innerHTML, so questions typed by visitors cannot inject markup.
 */
(function () {
  "use strict";

  const base = ((window.ARIVAZHAI_CONFIG && window.ARIVAZHAI_CONFIG.apiBaseUrl) || "").replace(/\/+$/, "");
  const KEY = "arivazhai-admin";
  const $ = (selector, root) => (root || document).querySelector(selector);
  const $$ = (selector, root) => [...(root || document).querySelectorAll(selector)];
  const WEEKDAYS = ["Mon", "Tue", "Wed", "Thu", "Fri", "Sat", "Sun"];
  let token = "";
  try {
    token = window.sessionStorage.getItem(KEY) || "";
  } catch (e) {
    /* storage blocked: sign in each time */
  }

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    Object.entries(attrs || {}).forEach(([key, value]) => {
      if (value == null || value === false) return;
      if (key === "text") node.textContent = value;
      else if (key === "class") node.className = value;
      else if (key.startsWith("on")) node.addEventListener(key.slice(2), value);
      else node.setAttribute(key, value === true ? "" : value);
    });
    [].concat(children || []).forEach((child) => child != null && node.append(child));
    return node;
  }

  async function call(path, options) {
    const response = await fetch(base + path, {
      ...(options || {}),
      headers: { "Content-Type": "application/json", Authorization: "Bearer " + token, ...((options && options.headers) || {}) },
    });
    if (response.status === 401) {
      signOut("Please sign in again.");
      throw new Error("signed out");
    }
    if (!response.ok) {
      let detail = "";
      try {
        detail = (await response.json()).detail;
      } catch (e) {
        /* not JSON */
      }
      throw new Error(typeof detail === "string" && detail ? detail : "The server said " + response.status + ".");
    }
    return response;
  }
  const getJson = async (path) => (await call(path)).json();

  function toast(text, ms) {
    const box = $(".admin-toast");
    box.textContent = text;
    box.hidden = false;
    clearTimeout(toast.timer);
    toast.timer = setTimeout(() => (box.hidden = true), ms || 4000);
  }

  const when = (iso) => {
    if (!iso) return "";
    const date = new Date(iso);
    return isNaN(date) ? iso : date.toLocaleString("en-IN", { day: "numeric", month: "short", hour: "numeric", minute: "2-digit" });
  };

  // ------------------------------------------------------------------ signing in
  function signedIn(value) {
    document.body.classList.toggle("is-admin", value);
  }

  function signOut(message) {
    token = "";
    try {
      window.sessionStorage.removeItem(KEY);
    } catch (e) {
      /* fine */
    }
    signedIn(false);
    $(".admin-login__status").textContent = message || "";
    $("#admin-password").focus();
  }

  $(".admin-login").addEventListener("submit", async (event) => {
    event.preventDefault();
    const status = $(".admin-login__status");
    const button = $(".admin-login button");
    token = $("#admin-password").value.trim();
    if (!token) {
      status.textContent = "Please enter the admin password.";
      return;
    }
    button.disabled = true;
    status.textContent = "";
    try {
      const response = await fetch(base + "/api/admin/check", { headers: { Authorization: "Bearer " + token } });
      if (response.status === 503) throw new Error("The admin panel is switched off: set ADMIN_TOKEN in the server's .env and restart it.");
      if (response.status === 429) throw new Error("Too many attempts. Please wait a minute.");
      if (!response.ok) throw new Error("Wrong password.");
      try {
        window.sessionStorage.setItem(KEY, token);
      } catch (e) {
        /* this tab only */
      }
      $("#admin-password").value = "";
      signedIn(true);
      loadAll();
    } catch (err) {
      token = "";
      status.textContent = err.message === "Failed to fetch" ? "Cannot reach the server." : err.message;
    } finally {
      button.disabled = false;
    }
  });
  $(".admin-signout").addEventListener("click", () => signOut(""));

  // ------------------------------------------------------------------ tabs
  function showTab(tab) {
    $$(".admin-tab").forEach((t) => {
      const on = t === tab;
      t.setAttribute("aria-selected", String(on));
      t.tabIndex = on ? 0 : -1;
      $("#" + t.getAttribute("aria-controls")).hidden = !on;
    });
  }
  $$(".admin-tab").forEach((tab, index, tabs) => {
    tab.addEventListener("click", () => showTab(tab));
    tab.addEventListener("keydown", (event) => {
      const step = event.key === "ArrowRight" ? 1 : event.key === "ArrowLeft" ? -1 : 0;
      if (!step) return;
      const next = tabs[(index + step + tabs.length) % tabs.length];
      next.focus();
      showTab(next);
    });
  });

  // ------------------------------------------------------------------ dashboard
  function tile(label, value, note) {
    return el("div", { class: "admin-card flex flex-col gap-1 !p-4" }, [
      el("span", { class: "text-[0.8rem] font-semibold tracking-[0.03em] text-muted uppercase", text: label }),
      el("span", { class: "font-heading text-[2rem] leading-none font-bold text-ink", text: value == null ? "–" : String(value) }),
      note ? el("span", { class: "text-[0.8rem] text-muted", text: note }) : null,
    ]);
  }

  /** A single-series column chart: one hue, thin columns from one baseline, hover/focus tooltip, a table view. */
  function columnChart(figure, title, labels, values, describe) {
    figure.textContent = "";
    const max = Math.max(1, ...values);
    const total = values.reduce((a, b) => a + b, 0);
    const tip = $(".admin-tip");
    const plot = el("div", { class: "admin-plot", role: "img", "aria-label": title + ": " + total + " questions in all" });
    values.forEach((value, i) => {
      const label = describe(labels[i], value);
      const column = el("button", { type: "button", class: "admin-col", "aria-label": label, "data-value": String(value) }, [
        el("span", { class: "admin-bar", style: "height:" + (value ? Math.max(2, (100 * value) / max) : 0) + "%" }),
      ]);
      const show = () => {
        const box = column.getBoundingClientRect();
        tip.textContent = label;
        tip.hidden = false;
        tip.style.left = Math.min(window.innerWidth - tip.offsetWidth - 8, Math.max(8, box.left + box.width / 2 - tip.offsetWidth / 2)) + "px";
        tip.style.top = Math.max(8, box.top - tip.offsetHeight - 8) + "px";
      };
      const hide = () => (tip.hidden = true);
      column.addEventListener("mouseenter", show);
      column.addEventListener("focus", show);
      column.addEventListener("mouseleave", hide);
      column.addEventListener("blur", hide);
      plot.append(column);
    });
    const step = Math.ceil(labels.length / 12); // axis labels that never collide
    const axis = el("div", { class: "admin-axis", "aria-hidden": "true" },
      labels.map((l, i) => el("span", { text: i % step === 0 ? String(l) : "" })));
    const table = el("details", { class: "mt-3 text-[0.85rem]" }, [
      el("summary", { class: "cursor-pointer text-link", text: "Show as a table" }),
      el("table", { class: "admin-table mt-2" }, [
        el("thead", null, el("tr", null, [el("th", { text: "When" }), el("th", { text: "Questions" })])),
        el("tbody", null, labels.map((l, i) => el("tr", null, [el("td", { text: String(l) }), el("td", { text: String(values[i]) })]))),
      ]),
    ]);
    figure.append(
      el("figcaption", { class: "admin-h2", text: title }),
      el("p", { class: "m-0 mb-3 text-[0.85rem] text-muted", text: total ? "Peak: " + describe(labels[values.indexOf(Math.max(...values))], max) : "No questions in this period yet." }),
      el("div", { class: "admin-chart" }, [
        el("div", { class: "admin-scale", "aria-hidden": "true" }, [el("span", { text: String(max) }), el("span", { text: "0" })]),
        el("div", { class: "min-w-0 flex-1" }, [plot, axis]),
      ]),
      table,
    );
  }

  const hourLabel = (h) => (h % 12 === 0 ? 12 : h % 12) + (h < 12 ? " AM" : " PM");

  function questionsTable(rows, columns) {
    if (!rows.length) return el("p", { class: "m-0 text-muted", text: "Nothing yet." });
    return el("table", { class: "admin-table w-full" }, [
      el("thead", null, el("tr", null, columns.map((c) => el("th", { text: c[0], class: c[2] || "" })))),
      el("tbody", null, rows.map((row) => el("tr", null, columns.map((c) => el("td", { text: c[1](row), class: c[2] || "" }))))),
    ]);
  }

  async function loadDashboard() {
    const days = $(".admin-days").value;
    const data = await getJson("/api/admin/dashboard?days=" + days);
    const t = data.totals;
    $(".admin-tiles").replaceChildren(
      tile("Questions", t.questions, "last " + data.days + " days"),
      tile("Today", t.today),
      tile("Last 7 days", t.last_7_days),
      tile("Answered", t.answered_share == null ? null : t.answered_share + "%", "from the website or your answers"),
      tile("Waiting for an answer", t.unanswered_open, "questions the website does not cover"),
      tile("Visitors", t.users, "signed in with name and number"),
      tile("Answer time", t.avg_seconds == null ? null : t.avg_seconds + " s", t.median_seconds == null ? "" : "median " + t.median_seconds + " s"),
      tile("Helpful / not helpful", t.helpful + " / " + t.not_helpful, "👍 / 👎 under the answers"),
    );
    columnChart($('[data-chart="by_hour"]'), "When people ask: hour of the day (" + data.timezone + ")",
      data.by_hour.map((_, h) => hourLabel(h)), data.by_hour, (l, v) => l + ": " + v + " question" + (v === 1 ? "" : "s"));
    columnChart($('[data-chart="by_weekday"]'), "Day of the week", WEEKDAYS, data.by_weekday,
      (l, v) => l + ": " + v + " question" + (v === 1 ? "" : "s"));
    columnChart($('[data-chart="daily"]'), "Questions per day",
      data.daily.map((d) => new Date(d.date + "T00:00").toLocaleDateString("en-IN", { day: "numeric", month: "short" })),
      data.daily.map((d) => d.count), (l, v) => l + ": " + v + " question" + (v === 1 ? "" : "s"));
    $(".admin-top").replaceChildren(questionsTable(data.top_questions, [
      ["Question", (r) => r.question],
      ["Asked", (r) => String(r.count), "text-right"],
      ["Last asked", (r) => when(r.last_asked), "whitespace-nowrap"],
    ]));
    $(".admin-down").replaceChildren(questionsTable(data.not_helpful, [
      ["Question", (r) => r.question],
      ["What was wrong", (r) => r.comment || "–"],
      ["When", (r) => when(r.at), "whitespace-nowrap"],
    ]));
    $('[data-count="unanswered"]').textContent = t.unanswered_open ? String(t.unanswered_open) : "";
    $(".admin-users-count").textContent = t.users + " visitor" + (t.users === 1 ? "" : "s") + " so far.";
    renderUnanswered(data.unanswered);
  }

  // ------------------------------------------------------------------ unanswered questions and answers
  function renderUnanswered(rows) {
    const list = $(".admin-unanswered");
    list.replaceChildren();
    if (!rows.length) {
      list.append(el("p", { class: "m-0 text-muted", text: "No unanswered questions. 🎉" }));
      return;
    }
    rows.forEach((row) => {
      list.append(el("div", { class: "admin-card flex flex-wrap items-center gap-3 !p-4" + (row.answered ? " opacity-70" : "") }, [
        el("div", { class: "min-w-0 flex-1" }, [
          el("p", { class: "m-0 font-semibold text-ink", dir: "auto", text: row.question }),
          el("p", { class: "m-0 text-[0.85rem] text-muted", text: "Asked " + row.count + " time" + (row.count === 1 ? "" : "s") + " · last " + when(row.last_asked) }),
        ]),
        row.answered
          ? el("span", { class: "rounded-full bg-[#e6f4ea] px-3 py-1 text-[0.85rem] font-semibold text-[#1e5e2f]", text: "✓ Answered" })
          : el("button", { type: "button", class: "min-h-10 cursor-pointer rounded-xl border-0 bg-gold px-4 font-bold text-navy-dark hover:bg-gold-dark",
                           text: "Answer", onclick: () => openEditor({ question: row.question, resolves: [row.question] }) }),
      ]));
    });
  }

  async function loadAnswers() {
    const answers = await getJson("/api/admin/answers");
    const list = $(".admin-answers");
    list.replaceChildren();
    if (!answers.length) {
      list.append(el("p", { class: "m-0 text-muted", text: "No answers yet. Answer a question from the Unanswered questions tab, or add one here." }));
      return;
    }
    answers.forEach((entry) => {
      list.append(el("article", { class: "admin-card flex flex-col gap-2 !p-4" }, [
        el("h2", { class: "m-0 text-[1.05rem] text-navy", dir: "auto", text: entry.question }),
        el("p", { class: "m-0 whitespace-pre-line", dir: "auto", text: entry.answer }),
        el("div", { class: "flex flex-wrap items-center gap-2 text-[0.85rem] text-muted" }, [
          el("span", { text: "Updated " + when(entry.updated_at) }),
          el("button", { type: "button", class: "ml-auto min-h-9 cursor-pointer rounded-lg border border-field bg-white px-3 font-semibold text-navy",
                         text: "Edit", onclick: () => openEditor(entry) }),
          el("button", { type: "button", class: "min-h-9 cursor-pointer rounded-lg border border-danger bg-white px-3 font-semibold text-danger-text",
                         text: "Delete", onclick: () => removeAnswer(entry) }),
        ]),
      ]));
    });
  }

  let editing = null;
  function openEditor(entry) {
    editing = entry || {};
    const dialog = $(".admin-editor");
    $("#editor-title").textContent = editing.id ? "Edit the answer" : "Answer a question";
    $("#editor-question").value = editing.question || "";
    $("#editor-answer").value = editing.answer || "";
    $(".admin-editor__status").textContent = "";
    if (dialog.showModal) dialog.showModal();
    else dialog.setAttribute("open", "");
    (editing.question ? $("#editor-answer") : $("#editor-question")).focus();
  }
  const closeEditor = () => ($(".admin-editor").close ? $(".admin-editor").close() : $(".admin-editor").removeAttribute("open"));
  $(".admin-editor__cancel").addEventListener("click", closeEditor);
  $(".admin-new").addEventListener("click", () => openEditor(null));

  /** After saving: Arivazhai chunks and indexes the answer in the background; say when it is live. */
  async function followIndexing(jobId) {
    if (!jobId || jobId === "queued") {
      toast("Saved. Arivazhai will learn it as soon as the current update finishes.", 6000);
      return;
    }
    toast("Saved. Arivazhai is learning it (splitting into passages and indexing)…", 60000);
    for (let i = 0; i < 120; i++) {
      await new Promise((r) => setTimeout(r, 1500));
      let job;
      try {
        job = await getJson("/api/admin/jobs/" + encodeURIComponent(jobId));
      } catch (e) {
        return;
      }
      if (job.state === "finished") {
        toast("Ready: visitors now get this answer.", 5000);
        return;
      }
      if (job.state === "failed") {
        toast("Saved, but indexing failed: " + (job.error || "see the server log") + ".", 10000);
        return;
      }
    }
  }

  $(".admin-editor form").addEventListener("submit", async (event) => {
    event.preventDefault();
    const question = $("#editor-question").value.trim();
    const answer = $("#editor-answer").value.trim();
    const status = $(".admin-editor__status");
    if (question.length < 3 || !answer) {
      status.textContent = "Please write both the question and the answer.";
      return;
    }
    const button = $('.admin-editor button[type="submit"]');
    button.disabled = true;
    try {
      const body = JSON.stringify({ question: question, answer: answer, resolves: editing.resolves || [] });
      const response = await call(editing.id ? "/api/admin/answers/" + encodeURIComponent(editing.id) : "/api/admin/answers",
                                  { method: editing.id ? "PUT" : "POST", body: body });
      const saved = await response.json();
      closeEditor();
      loadAll();
      followIndexing(saved.indexing);
    } catch (err) {
      if (err.message !== "signed out") status.textContent = err.message;
    } finally {
      button.disabled = false;
    }
  });

  async function removeAnswer(entry) {
    if (!window.confirm("Delete this answer? Arivazhai will stop giving it.\n\n" + entry.question)) return;
    try {
      const saved = await (await call("/api/admin/answers/" + encodeURIComponent(entry.id), { method: "DELETE" })).json();
      loadAll();
      followIndexing(saved.indexing);
    } catch (err) {
      if (err.message !== "signed out") toast(err.message);
    }
  }

  // ------------------------------------------------------------------ visitors
  $(".admin-download").addEventListener("click", async () => {
    const status = $(".admin-download__status");
    status.textContent = "Preparing the file…";
    try {
      const blob = await (await call("/api/admin/users.xlsx")).blob();
      const url = URL.createObjectURL(blob);
      const link = el("a", { href: url, download: "arivazhai-users-" + new Date().toISOString().slice(0, 10) + ".xlsx" });
      document.body.append(link);
      link.click();
      link.remove();
      setTimeout(() => URL.revokeObjectURL(url), 10000);
      status.textContent = "Downloaded.";
    } catch (err) {
      if (err.message !== "signed out") status.textContent = err.message;
    }
  });

  // ------------------------------------------------------------------ start
  async function loadAll() {
    try {
      await Promise.all([loadDashboard(), loadAnswers()]);
    } catch (err) {
      if (err.message !== "signed out") toast("Could not load: " + err.message, 8000);
    }
  }
  $(".admin-days").addEventListener("change", loadAll);
  $(".admin-refresh").addEventListener("click", loadAll);

  showTab($(".admin-tab"));
  if (token) {
    signedIn(true);
    loadAll();
  }
})();
