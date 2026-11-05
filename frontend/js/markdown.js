/*
 * A small, safe Markdown renderer for the answers: paragraphs, headings, bullet and numbered lists
 * (nested), tables, block quotes, code, horizontal rules, **bold**, *italic*, `code`, links and bare
 * web addresses. Every element is built with document.createElement and every text with
 * textContent, so nothing in an answer can become HTML or script. Images are never shown inline
 * (photos are shown as image cards), and only http(s) links are kept.
 */
(function (A) {
  "use strict";

  const TABLE_RULE = /^\s*\|?\s*:?-{1,}:?\s*(\|\s*:?-{1,}:?\s*)*\|?\s*$/;
  const LIST_ITEM = /^(\s*)([-*+]|\d{1,9}[.)])\s+(.*)$/;
  const HEADING = /^\s{0,3}(#{1,6})\s+(.*?)\s*#*\s*$/;
  const RULE = /^\s{0,3}([-*_])(\s*\1){2,}\s*$/;
  const FENCE = /^\s{0,3}(```|~~~)/;
  const QUOTE = /^\s{0,3}>\s?(.*)$/;
  /** "[[2]](https://... "Source 2: Admission")" - the citations linkCitations writes. */
  const CITATION_TEXT = /^\[(\d+|image \d+)\]$/;

  /** Only http(s) links, resolved against the official website. */
  function safeHref(href, base) {
    if (!href) return null;
    try {
      const url = new URL(href, base || (A.site && A.site.officialUrl) || window.location.href);
      return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : null;
    } catch (e) {
      return null;
    }
  }

  /** Raw HTML in an answer is not shown as HTML: a line break stays a line break, other tags are dropped. */
  function stripHtml(text) {
    return text.replace(/<br\s*\/?>/gi, "\n").replace(/<\/?[a-z][a-z0-9-]*(\s[^<>]*)?\/?>/gi, "");
  }

  function splitRow(line) {
    let row = line.trim();
    if (row.startsWith("|")) row = row.slice(1);
    if (row.endsWith("|") && !row.endsWith("\\|")) row = row.slice(0, -1);
    const cells = [];
    let cell = "";
    for (let i = 0; i < row.length; i++) {
      if (row[i] === "\\" && row[i + 1] === "|") {
        cell += "|";
        i++;
      } else if (row[i] === "|") {
        cells.push(cell.trim());
        cell = "";
      } else {
        cell += row[i];
      }
    }
    cells.push(cell.trim());
    return cells;
  }

  function alignOf(spec) {
    const s = spec.trim();
    if (s.startsWith(":") && s.endsWith(":")) return "center";
    if (s.endsWith(":")) return "right";
    if (s.startsWith(":")) return "left";
    return "";
  }

  // ------------------------------------------------------------------ inline
  const INLINE_PATTERNS = [
    // `code`
    { re: /`([^`]+)`/y, make: (m) => el("code", null, [document.createTextNode(m[1])]) },
    // ![alt](src) - not shown
    { re: /!\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(([^()\s]*(?:\([^()\s]*\)[^()\s]*)*)(?:\s+"((?:[^"\\]|\\.)*)")?\)/y, make: () => null },
    // [text](url "title"); the text may hold one level of brackets: [[2]](...)
    { re: /\[((?:[^\[\]]|\[[^\[\]]*\])*)\]\(\s*<?([^()\s<>]*(?:\([^()\s]*\)[^()\s<>]*)*)>?(?:\s+"((?:[^"\\]|\\.)*)")?\s*\)/y, make: (m, opts) => link(m[1], m[2], m[3] ? m[3].replace(/\\(.)/g, "$1") : "", opts) },
    // <https://...> and bare https://... addresses
    { re: /<(https?:\/\/[^\s<>]+)>/y, make: (m, opts) => bareLink(m[1], opts) },
    { re: /https?:\/\/[^\s<>()\[\]]*[^\s<>()\[\].,;:!?'"*_]/y, make: (m, opts) => bareLink(m[0], opts) },
    // **bold** / __bold__
    { re: /\*\*(?=\S)([\s\S]*?\S)\*\*/y, make: (m, opts) => el("strong", null, inline(m[1], opts)) },
    { re: /__(?=\S)([\s\S]*?\S)__(?!\w)/y, make: (m, opts) => el("strong", null, inline(m[1], opts)) },
    // *italic* / _italic_ (not inside words: "file_name")
    { re: /\*(?=[^\s*])([^*]*?[^\s*])\*/y, make: (m, opts) => el("em", null, inline(m[1], opts)) },
    { re: /_(?=[^\s_])([^_]*?[^\s_])_(?!\w)/y, make: (m, opts) => el("em", null, inline(m[1], opts)), wordStart: true },
    // ~~strike~~
    { re: /~~(?=\S)([\s\S]*?\S)~~/y, make: (m, opts) => el("del", null, inline(m[1], opts)) },
  ];

  function el(tag, attrs, children) {
    const node = document.createElement(tag);
    if (attrs) for (const key of Object.keys(attrs)) if (attrs[key] != null && attrs[key] !== "") node.setAttribute(key, attrs[key]);
    if (children) for (const child of children) if (child) node.appendChild(child);
    return node;
  }

  function link(text, href, title, opts) {
    const children = inline(text, Object.assign({}, opts, { inLink: true })); // no link inside a link
    if (href.startsWith("#")) {
      // [[image 2]](#m1-I2): jumps to the image card in the same answer
      return el("a", { href: href, class: "citation citation--image" }, children);
    }
    const safe = safeHref(href);
    if (!safe) return fragment(children);
    const isCitation = CITATION_TEXT.test(text);
    return el(
      "a",
      {
        href: safe,
        title: title || null,
        target: "_blank",
        rel: "noopener noreferrer",
        class: isCitation ? "citation" : null,
        "aria-label": isCitation && title ? title + " (opens in a new tab)" : null,
      },
      children,
    );
  }

  function bareLink(url, opts) {
    const safe = !opts.inLink && safeHref(url);
    if (!safe) return document.createTextNode(url);
    return el("a", { href: safe, target: "_blank", rel: "noopener noreferrer" }, [document.createTextNode(url)]);
  }

  function fragment(children) {
    const frag = document.createDocumentFragment();
    for (const child of children) if (child) frag.appendChild(child);
    return frag;
  }

  /** Inline Markdown to DOM nodes. A backslash keeps the next mark as text ("\*"). */
  function inline(text, opts) {
    const nodes = [];
    let plain = "";
    const flush = () => {
      if (plain) nodes.push(document.createTextNode(plain));
      plain = "";
    };
    let i = 0;
    outer: while (i < text.length) {
      const ch = text[i];
      if (ch === "\\" && i + 1 < text.length && /[\\`*_{}\[\]()#+\-.!|~<>]/.test(text[i + 1])) {
        plain += text[i + 1];
        i += 2;
        continue;
      }
      if (ch === "\n") {
        // a line break inside a paragraph is a space, as in Markdown; two spaces before it keep it
        if (/ {2,}$/.test(plain)) {
          plain = plain.replace(/ +$/, "");
          flush();
          nodes.push(document.createElement("br"));
        } else {
          plain += " ";
        }
        i++;
        continue;
      }
      if ("`![<h*_~".includes(ch)) {
        for (const pattern of INLINE_PATTERNS) {
          if (pattern.wordStart && i > 0 && /\w/.test(text[i - 1])) continue;
          pattern.re.lastIndex = i;
          const m = pattern.re.exec(text);
          if (m && m.index === i) {
            flush();
            const node = pattern.make(m, opts);
            if (node) nodes.push(node);
            i += m[0].length;
            continue outer;
          }
        }
      }
      plain += ch;
      i++;
    }
    flush();
    return nodes;
  }

  // ------------------------------------------------------------------ blocks
  function isTableStart(lines, i) {
    return lines[i].includes("|") && i + 1 < lines.length && TABLE_RULE.test(lines[i + 1]) && lines[i + 1].includes("-");
  }

  function startsBlock(lines, i) {
    const line = lines[i];
    return HEADING.test(line) || RULE.test(line) || FENCE.test(line) || QUOTE.test(line) || LIST_ITEM.test(line) || isTableStart(lines, i);
  }

  function table(lines, i, opts) {
    const head = splitRow(lines[i]);
    const aligns = splitRow(lines[i + 1]).map(alignOf);
    const thead = el("thead", null, [el("tr", null, head.map((cell, c) => el("th", { style: aligns[c] ? "text-align:" + aligns[c] : null }, inline(cell, opts))))]);
    const rows = [];
    i += 2;
    while (i < lines.length && lines[i].trim() && lines[i].includes("|")) {
      const cells = splitRow(lines[i]);
      const tr = el("tr");
      for (let c = 0; c < head.length; c++) {
        tr.appendChild(el("td", { style: aligns[c] ? "text-align:" + aligns[c] : null }, inline(cells[c] || "", opts)));
      }
      rows.push(tr);
      i++;
    }
    return { node: el("table", null, [thead, el("tbody", null, rows)]), next: i };
  }

  /** Lists, nested by indentation; a line indented under an item continues it. */
  function list(lines, i, opts) {
    const first = LIST_ITEM.exec(lines[i]);
    const indent = first[1].replace(/\t/g, "    ").length;
    const ordered = /\d/.test(first[2]);
    const start = ordered ? parseInt(first[2], 10) : 1;
    const node = el(ordered ? "ol" : "ul", ordered && start !== 1 ? { start: String(start) } : null);
    let item = null;
    let text = [];
    const finish = () => {
      if (!item) return;
      item.insertBefore(fragment(inline(text.join("\n"), opts)), item.firstChild);
      text = [];
    };
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) {
        // a blank line ends the list unless the list goes on after it
        let j = i + 1;
        while (j < lines.length && !lines[j].trim()) j++;
        const m = j < lines.length && LIST_ITEM.exec(lines[j]);
        if (m && m[1].replace(/\t/g, "    ").length >= indent) {
          i = j;
          continue;
        }
        break;
      }
      const m = LIST_ITEM.exec(line);
      if (m) {
        const depth = m[1].replace(/\t/g, "    ").length;
        if (depth < indent) break;
        if (depth >= indent + 2 && item) {
          finish();
          const nested = list(lines, i, opts);
          item.appendChild(nested.node);
          i = nested.next;
          continue;
        }
        if (/\d/.test(m[2]) !== ordered) break;
        finish();
        item = el("li");
        node.appendChild(item);
        text = [m[3]];
        i++;
        continue;
      }
      if (/^\s+\S/.test(line) && item && !startsBlock(lines, i)) {
        text.push(line.trim());
        i++;
        continue;
      }
      if (item && !startsBlock(lines, i) && text.length) {
        text.push(line.trim()); // a wrapped line of the item
        i++;
        continue;
      }
      break;
    }
    finish();
    return { node: node, next: i };
  }

  function blocks(lines, opts) {
    const out = [];
    let i = 0;
    while (i < lines.length) {
      const line = lines[i];
      if (!line.trim()) {
        i++;
        continue;
      }
      let m;
      if (FENCE.test(line)) {
        const fence = FENCE.exec(line)[1];
        const code = [];
        i++;
        while (i < lines.length && !lines[i].trim().startsWith(fence)) code.push(lines[i++]);
        i++;
        out.push(el("pre", null, [el("code", null, [document.createTextNode(code.join("\n"))])]));
        continue;
      }
      if ((m = HEADING.exec(line))) {
        out.push(el("h" + m[1].length, null, inline(m[2], opts)));
        i++;
        continue;
      }
      if (isTableStart(lines, i)) {
        const t = table(lines, i, opts);
        out.push(t.node);
        i = t.next;
        continue;
      }
      if (RULE.test(line)) {
        out.push(el("hr"));
        i++;
        continue;
      }
      if (QUOTE.test(line)) {
        const quoted = [];
        while (i < lines.length && QUOTE.test(lines[i])) quoted.push(QUOTE.exec(lines[i++])[1]);
        out.push(el("blockquote", null, blocks(quoted, opts)));
        continue;
      }
      if (LIST_ITEM.test(line)) {
        const l = list(lines, i, opts);
        out.push(l.node);
        i = l.next;
        continue;
      }
      const para = [];
      while (i < lines.length && lines[i].trim() && (para.length === 0 || !startsBlock(lines, i))) para.push(lines[i++]);
      out.push(el("p", null, inline(para.join("\n").trim(), opts)));
    }
    return out;
  }

  /** Markdown text -> a DocumentFragment of safe elements. */
  function render(markdown, opts) {
    const lines = stripHtml(String(markdown || "")).replace(/\r\n?/g, "\n").split("\n");
    return fragment(blocks(lines, opts || {}));
  }

  A.markdown = { render: render, safeHref: safeHref, CITATION_TEXT: CITATION_TEXT };
})((window.Arivazhai = window.Arivazhai || {}));
