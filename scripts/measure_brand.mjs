#!/usr/bin/env node
/**
 * Measure the official website's branding from the RENDERED page (computed styles)
 * and write the frontend brand files. Preferred over extract_brand.py for page-builder
 * sites (Elementor etc.) whose CSS uses generated class names.
 *
 *   cd frontend && node ../scripts/measure_brand.mjs [--url https://aaaenggcoll.ac.in/] [--inner /about-us/] [--dry-run]
 *
 * Requires the frontend dev dependencies (@playwright/test) and a Chromium:
 *   npx playwright install chromium        (or set PLAYWRIGHT_CHROMIUM_PATH)
 * Honours HTTPS_PROXY when set.
 *
 * Writes frontend/src/brand/brand.json, frontend/src/brand/brand.css and
 * frontend/public/brand/{logo,banner,favicon}.*  Colours used for text are checked
 * against WCAG AA (4.5:1) and nudged lighter/darker only when the measured pair fails;
 * every adjustment is reported.
 */
import { mkdirSync, readFileSync, writeFileSync } from "node:fs";
import { createRequire } from "node:module";
import { dirname, join } from "node:path";
import { fileURLToPath } from "node:url";

const ROOT = join(dirname(fileURLToPath(import.meta.url)), "..");
// Playwright is a dev dependency of the frontend, so resolve it from there.
const { chromium } = createRequire(join(ROOT, "frontend", "package.json"))("@playwright/test");
const BRAND_DIR = join(ROOT, "frontend", "src", "brand");
const PUBLIC_DIR = join(ROOT, "frontend", "public", "brand");
const arg = (name, fallback) => {
  const i = process.argv.indexOf(name);
  return i > -1 ? process.argv[i + 1] : fallback;
};
const URL_BASE = arg("--url", "https://aaaenggcoll.ac.in/");
const INNER = new URL(arg("--inner", "/about-us/"), URL_BASE).toString();
const DRY = process.argv.includes("--dry-run");
const report = [];

// ------------------------------------------------------------------ colour maths
const parseRgb = (s) => {
  const m = /rgba?\(\s*(\d+)[,\s]+(\d+)[,\s]+(\d+)(?:[,\s/]+([\d.]+))?/.exec(s || "");
  if (!m) return null;
  if (m[4] !== undefined && Number(m[4]) < 0.5) return null;
  return [Number(m[1]), Number(m[2]), Number(m[3])];
};
const hex = (rgb) => "#" + rgb.map((v) => Math.round(Math.max(0, Math.min(255, v))).toString(16).padStart(2, "0")).join("");
const toRgb = (h) => [1, 3, 5].map((i) => parseInt(h.slice(i, i + 2), 16));
const lum = (h) => {
  const c = toRgb(h).map((v) => v / 255).map((v) => (v <= 0.03928 ? v / 12.92 : ((v + 0.055) / 1.055) ** 2.4));
  return 0.2126 * c[0] + 0.7152 * c[1] + 0.0722 * c[2];
};
const contrast = (a, b) => {
  const [x, y] = [lum(a), lum(b)].sort((p, q) => q - p);
  return (x + 0.05) / (y + 0.05);
};
const mix = (a, b, t) => hex(toRgb(a).map((v, i) => v + (toRgb(b)[i] - v) * t));
const darken = (h, t = 0.18) => mix(h, "#000000", t);
const readableOn = (bg) => (contrast(bg, "#ffffff") >= contrast(bg, "#151414") ? "#ffffff" : "#151414");
/** Keep the measured colour when it passes; otherwise move it towards white/black until it does. */
function ensureContrast(fg, bg, label, min = 4.5) {
  if (contrast(fg, bg) >= min) return fg;
  if (lum(fg) > 0.95 || lum(fg) < 0.01) {
    // pure white/black text that fails: flip to the readable extreme rather than a muddy grey
    const flipped = readableOn(bg);
    report.push(`${label}: measured ${fg} on ${bg} is ${contrast(fg, bg).toFixed(2)}:1; using ${flipped} (${contrast(flipped, bg).toFixed(2)}:1) for WCAG AA`);
    return flipped;
  }
  const target = lum(bg) < 0.4 ? "#ffffff" : "#000000";
  for (let t = 0.05; t <= 1; t += 0.05) {
    const c = mix(fg, target, t);
    if (contrast(c, bg) >= min) {
      report.push(`${label}: measured ${fg} on ${bg} is ${contrast(fg, bg).toFixed(2)}:1; adjusted to ${c} (${contrast(c, bg).toFixed(2)}:1) for WCAG AA`);
      return c;
    }
  }
  return target;
}

// ------------------------------------------------------------------ page measurement
async function measure(page) {
  return page.evaluate(() => {
    const visible = (el) => { const r = el.getBoundingClientRect(); return r.width > 4 && r.height > 4; };
    const style = (el) => {
      if (!el) return null;
      const s = getComputedStyle(el);
      return { color: s.color, bg: s.backgroundColor, bgImage: s.backgroundImage, font: s.fontFamily, size: s.fontSize,
               weight: s.fontWeight, transform: s.textTransform, radius: s.borderTopLeftRadius, text: (el.innerText || "").trim() };
    };
    const bgBehind = (el) => {
      while (el && el !== document.documentElement) {
        const s = getComputedStyle(el);
        if (s.backgroundColor && !/rgba\(\d+, \d+, \d+, 0\)/.test(s.backgroundColor) && s.backgroundColor !== "transparent") return s.backgroundColor;
        el = el.parentElement;
      }
      return "rgb(255, 255, 255)";
    };
    const header = document.querySelector("header, [data-elementor-type='header'], .site-header") || document.body;
    const footer = document.querySelector("footer, [data-elementor-type='footer'], .site-footer");

    // main menu = the header list with the most top-level items
    const lists = [...header.querySelectorAll("ul")].filter((ul) => !ul.parentElement.closest("ul") && visible(ul));
    const menu = lists.map((ul) => [...ul.children].filter((li) => li.tagName === "LI")).sort((a, b) => b.length - a.length)[0] || [];
    const nav = menu.map((li) => {
      const a = li.querySelector("a");
      const label = (a?.textContent || "").trim().replace(/\s+/g, " ");
      const children = [...li.querySelectorAll(":scope ul > li > a")].map((x) => ({ label: x.textContent.trim().replace(/\s+/g, " "), href: x.href }))
        .filter((c) => c.label && /^https?:/.test(c.href));
      return { label, href: a && /^https?:/.test(a.href) && !a.href.endsWith("#") ? a.href : "", children };
    }).filter((i) => i.label);
    const firstLink = menu[0]?.querySelector("a span, a");

    // logo: the widest image near the top of the header
    const imgs = [...header.querySelectorAll("img")].filter((i) => visible(i) && i.getBoundingClientRect().top < 200)
      .sort((a, b) => b.getBoundingClientRect().width - a.getBoundingClientRect().width);
    const logo = imgs[0];

    // header buttons & notes outside the menu
    const menuLinks = new Set(menu.flatMap((li) => [...li.querySelectorAll("a")]));
    const buttons = [...header.querySelectorAll("a")].filter((a) => !menuLinks.has(a) && visible(a) && a.textContent.trim() && !a.querySelector("img"))
      .map((a) => ({ label: a.textContent.trim().replace(/\s+/g, " "), href: a.href, style: { ...style(a), bg: bgBehind(a) } }))
      .filter((b, i, all) => all.findIndex((x) => x.label === b.label) === i);
    const notes = [...header.querySelectorAll("h1,h2,h3,h4,h5,h6,p,span,div")]
      .filter((e) => visible(e) && e.children.length === 0 && !e.closest("a") && !e.closest("ul") && /\S/.test(e.textContent) && e.textContent.trim().length < 60)
      .map((e) => ({ text: e.textContent.trim(), style: style(e) }));

    // header background: largest painted area in the header that is not the menu bar
    let headerBg = null, best = 0;
    for (const el of [header, ...header.querySelectorAll("*")]) {
      const s = getComputedStyle(el); const r = el.getBoundingClientRect();
      if (r.top > 160 || r.height < 40) continue;
      const paint = s.backgroundImage !== "none" && s.backgroundImage.includes("gradient") ? s.backgroundImage : s.backgroundColor;
      if (!paint || /rgba\(\d+, \d+, \d+, 0\)/.test(paint)) continue;
      if (r.width * r.height > best) { best = r.width * r.height; headerBg = paint; }
    }

    // page banner (inner pages): first heading inside main painted on a coloured box
    const main = document.querySelector("main") || document.body;
    const bannerTitle = [...main.querySelectorAll("h1,h2")].find(visible);
    let bannerImage = null;
    for (let el = bannerTitle; el && el !== main.parentElement; el = el.parentElement) {
      const m = /url\(["']?([^"')]+)/.exec(getComputedStyle(el).backgroundImage);
      if (m) { bannerImage = m[1]; break; }
    }
    if (!bannerImage) {
      // page builders often paint the banner on a sibling section: take the first wide
      // background image (or image) near the top of the content area
      for (const el of main.querySelectorAll("*")) {
        const r = el.getBoundingClientRect();
        if (r.top > 600 || r.width < window.innerWidth * 0.6 || r.height < 150) continue;
        const bg = /url\(["']?([^"')]+)/.exec(getComputedStyle(el).backgroundImage);
        if (bg) { bannerImage = bg[1]; break; }
        if (el.tagName === "IMG") { bannerImage = el.currentSrc || el.src; break; }
      }
    }
    const contentHeading = [...main.querySelectorAll("h2,h3")].filter(visible).find((h) => h !== bannerTitle && bgBehind(h) === "rgb(255, 255, 255)");
    const para = [...main.querySelectorAll("p")].find((p) => visible(p) && p.textContent.trim().length > 60);

    // footer columns
    let footerData = null;
    if (footer) {
      const headings = [...footer.querySelectorAll("h2,h3,h4,h5,.elementor-heading-title")].filter(visible);
      const columns = headings.map((h) => {
        let col = h.parentElement;
        while (col && col !== footer && col.querySelectorAll("a").length === 0) col = col.parentElement;
        const links = col && col !== footer ? [...col.querySelectorAll("a")].map((a) => ({ label: a.textContent.trim().replace(/\s+/g, " "), href: a.href }))
          .filter((l) => l.label && /^(https?|mailto|tel):/.test(l.href)) : [];
        return { title: h.textContent.trim(), links };
      }).filter((c, i, all) => all.findIndex((x) => x.title === c.title) === i);
      // most common rendered link colour (a single "Read more" link may be styled differently)
      const linkColors = {};
      for (const a of footer.querySelectorAll("a")) {
        if (!visible(a) || a.textContent.trim().length < 3) continue;
        const inner = a.querySelector("span") || a;
        const color = getComputedStyle(inner).color;
        linkColors[color] = (linkColors[color] || 0) + 1;
      }
      const linkColor = Object.entries(linkColors).sort((a, b) => b[1] - a[1])[0]?.[0] || null;
      const underline = headings[0] ? (() => { // decoration bar under footer headings (border or pseudo element)
        const s = getComputedStyle(headings[0]); const after = getComputedStyle(headings[0], "::after");
        const cands = [s.borderBottomColor && s.borderBottomWidth !== "0px" ? s.borderBottomColor : null, after.backgroundColor, after.borderBottomColor];
        for (let el = headings[0].parentElement, i = 0; el && i < 3; el = el.parentElement, i++) {
          const div = [...el.querySelectorAll(".elementor-divider-separator, hr")][0];
          if (div) cands.push(getComputedStyle(div).borderTopColor, getComputedStyle(div).backgroundColor);
        }
        return cands.find((c) => c && !/rgba\(\d+, \d+, \d+, 0\)/.test(c)) || null;
      })() : null;
      footerData = {
        bg: bgBehind(headings[0] || footer), heading: style(headings[0]), text: style([...footer.querySelectorAll("p, span")].find(visible)),
        link: linkColor ? { color: linkColor } : null, underline, columns, text_content: footer.innerText,
        social: [...footer.querySelectorAll("a")].filter((a) => /facebook|instagram|linkedin|youtube|twitter|x\.com/.test(a.href))
          .map((a) => ({ label: (a.textContent.trim() || a.getAttribute("aria-label") || new URL(a.href).hostname.replace("www.", "").split(".")[0]), href: a.href }))
          .filter((s, i, all) => all.findIndex((x) => x.href === s.href) === i),
      };
    }

    return {
      title: document.title,
      favicon: document.querySelector("link[rel~='icon']")?.href || null,
      body: { ...style(document.body), bg: getComputedStyle(document.body).backgroundColor }, paragraph: style(para),
      logo: logo ? { src: logo.currentSrc || logo.src, alt: logo.alt } : null,
      headerBg, nav, navLink: style(firstLink), navBg: firstLink ? bgBehind(firstLink) : null,
      buttons, notes,
      banner: bannerTitle ? { title: style(bannerTitle), boxBg: bgBehind(bannerTitle), image: bannerImage } : null,
      contentHeading: style(contentHeading),
      footer: footerData,
    };
  });
}

const firstFamily = (f) => (f || "").split(",")[0].replace(/["']/g, "").trim();
const SYSTEM_FONTS = /^(-apple-system|system-ui|BlinkMacSystemFont|Segoe UI|Roboto|Helvetica|Arial|sans-serif|serif)$/i;

async function main() {
  const executablePath = process.env.PLAYWRIGHT_CHROMIUM_PATH || undefined;
  const browser = await chromium.launch({ executablePath, proxy: process.env.HTTPS_PROXY ? { server: process.env.HTTPS_PROXY } : undefined });
  const context = await browser.newContext({ viewport: { width: 1366, height: 900 } });
  const page = await context.newPage();
  await page.goto(INNER, { waitUntil: "load", timeout: 90_000 });
  await page.waitForTimeout(2500);
  const m = await measure(page);

  const css = {};
  const set = (k, v) => { if (v) css[k] = v; };
  const c = (s) => { const rgb = parseRgb(s); return rgb ? hex(rgb) : null; };

  // primary = menu bar; buttons usually share it
  const primary = c(m.navBg);
  const button = m.buttons.map((b) => ({ ...b, bg: c(b.style.bg) })).find((b) => b.bg && b.bg !== "#ffffff");
  if (!primary) report.push("menu bar colour not found - keeping provisional value");
  set("--brand-primary", primary);
  set("--brand-primary-dark", primary && darken(primary));
  set("--brand-on-primary", primary && ensureContrast(c(m.navLink?.color) || readableOn(primary), primary, "menu text"));
  set("--brand-nav-bg", primary);
  set("--brand-nav-fg", primary && ensureContrast(c(m.navLink?.color) || "#ffffff", primary, "menu text"));
  set("--brand-nav-hover-bg", primary && darken(primary, 0.15));
  if (m.navLink) {
    set("--brand-nav-font-size", m.navLink.size);
    set("--brand-nav-font-weight", m.navLink.weight);
    set("--brand-nav-transform", /^[^a-z]*$/.test(m.navLink.text) ? "uppercase" : m.navLink.transform);
  }
  if (button) {
    set("--brand-button-bg", button.bg);
    set("--brand-button-fg", ensureContrast(c(button.style.color) || readableOn(button.bg), button.bg, "button text"));
  }
  const pill = m.buttons.map((b) => parseFloat(b.style.radius)).filter((r) => r > 0).sort((a, b) => b - a)[0];
  set("--brand-pill-radius", pill ? `${pill}px` : null);

  // header background (may be a gradient, e.g. the white → indigo diagonal)
  if (m.headerBg) {
    set("--brand-header-bg", m.headerBg);
    const colors = [...m.headerBg.matchAll(/rgba?\([^)]*\)/g)].map((x) => c(x[0])).filter(Boolean);
    const strong = colors.filter((x) => x !== "#ffffff").sort((a, b) => lum(a) - lum(b))[0];
    set("--brand-secondary", strong || null);
    set("--brand-header-fg", strong || primary);
  }
  const note = m.notes.find((n) => n.text.length > 6 && /\d/.test(n.text)) || null;

  // page banner box
  if (m.banner) {
    const box = c(m.banner.boxBg);
    if (box && box !== "#ffffff") {
      set("--brand-accent", box);
      set("--brand-banner-box-bg", box);
      set("--brand-banner-box-fg", ensureContrast(c(m.banner.title.color) || "#ffffff", box, "banner title", 3)); // large text: 3:1
      set("--brand-on-accent", ensureContrast(c(m.banner.title.color) || "#ffffff", box, "accent text"));
    }
    set("--brand-banner-transform", m.banner.title.transform);
  }

  // typography
  const bodyFont = firstFamily(m.paragraph?.font) || firstFamily(m.body.font);
  const headingFont = firstFamily(m.banner?.title.font) || firstFamily(m.contentHeading?.font) || bodyFont;
  const fonts = [...new Set([bodyFont, headingFont, firstFamily(m.navLink?.font)].filter((f) => f && !SYSTEM_FONTS.test(f)))];
  set("--brand-font-body", bodyFont && `"${bodyFont}", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif`);
  set("--brand-font-heading", headingFont && `"${headingFont}", system-ui, -apple-system, "Segoe UI", Roboto, Arial, sans-serif`);
  set("--brand-heading-weight", m.banner?.title.weight || m.contentHeading?.weight);
  set("--brand-text", c(m.paragraph?.color) || c(m.body.color));
  const pageBg = c(m.body.bg) || "#ffffff";
  set("--brand-page-bg", pageBg);
  set("--brand-subtle", mix(pageBg, "#000000", 0.045)); // light panel tone for chat bubbles
  set("--brand-heading", m.contentHeading && ensureContrast(c(m.contentHeading.color) || "#151414", pageBg, "content heading"));
  set("--brand-link", primary && ensureContrast(primary, pageBg, "link"));
  const stylesheets = fonts.length
    ? [`https://fonts.googleapis.com/css2?${fonts.map((f) => `family=${f.replace(/ /g, "+")}:wght@400;500;600;700`).join("&")}&display=swap`]
    : [];

  // footer
  const f = m.footer;
  if (f) {
    const fbg = c(f.bg);
    set("--brand-footer-bg", fbg);
    if (fbg) {
      set("--brand-footer-fg", ensureContrast(c(f.text?.color) || "#ffffff", fbg, "footer text"));
      set("--brand-footer-heading", ensureContrast(c(f.heading?.color) || "#ffffff", fbg, "footer heading"));
      set("--brand-footer-link", ensureContrast(c(f.link?.color) || "#ffffff", fbg, "footer link"));
      // heading underline bar; falls back to the accent when it can't be told apart from the heading text
      const bar = c(f.underline);
      set("--brand-footer-accent", bar && bar !== css["--brand-footer-heading"] ? bar : css["--brand-accent"]);
    }
  } else report.push("footer not found - keeping provisional footer colours");

  // contact details from the footer text
  const text = f?.text_content || "";
  const emails = [...new Set(text.match(/[\w.+-]+@[\w-]+(?:\.[\w-]+)+/g) || [])];
  const phones = [...new Set((text.match(/(?:\+91[\s-]?)?(?:0\d{2,4}[\s-]?\d{6,8}|1800\d{7}|[6-9]\d{9})/g) || []))];
  const addrLine = text.split("\n").map((l) => l.trim()).find((l) => /\b\d{3}\s?\d{3}\b/.test(l) && !/@/.test(l) && !/^\+?\d[\d\s,-]+$/.test(l));

  // assets
  mkdirSync(PUBLIC_DIR, { recursive: true });
  async function download(url, name) {
    if (!url || DRY) return null;
    try {
      const res = await context.request.get(url, { timeout: 60_000 });
      if (!res.ok()) throw new Error(`HTTP ${res.status()}`);
      const type = res.headers()["content-type"] || "";
      const ext = /png/.test(type) ? "png" : /jpe?g/.test(type) ? "jpg" : /webp/.test(type) ? "webp" : /svg/.test(type) ? "svg" : /icon|ico/.test(type) ? "ico" : null;
      if (!ext) throw new Error(`unexpected type ${type}`);
      writeFileSync(join(PUBLIC_DIR, `${name}.${ext}`), await res.body());
      return `/brand/${name}.${ext}`;
    } catch (e) {
      report.push(`could not download ${url}: ${e.message}`);
      return null;
    }
  }
  const logoPath = await download(m.logo?.src, "logo");
  const bannerPath = await download(m.banner?.image, "banner");
  const faviconPath = await download(m.favicon, "favicon");
  await browser.close();

  const collegeName = "AAA College of Engineering and Technology";
  const footerColumns = (f?.columns || []).filter((col) => col.links.length && !/contact/i.test(col.title))
    .map((col) => ({ title: col.title, links: col.links.filter((l) => /^https?:/.test(l.href) && !/read more/i.test(l.label)) }))
    .filter((col) => col.links.length);
  const brand = {
    measured: true,
    method: "rendered",
    note: `Measured from the rendered pages of ${URL_BASE} by scripts/measure_brand.mjs. Re-run after the website's design changes.`,
    source: URL_BASE,
    measured_at: new Date().toISOString().replace(/\.\d+Z$/, "Z"),
    college_name: collegeName,
    short_name: "AAACET",
    tagline: "",
    official_url: URL_BASE,
    logo: logoPath,
    logo_alt: `${collegeName} logo`,
    favicon: faviconPath,
    banner_image: bannerPath,
    header_note: note?.text || "",
    header_buttons: m.buttons.filter((b) => b.label.length < 30).map((b) => ({ label: b.label, href: b.href })),
    badges: [],
    // header buttons sometimes reappear in the (mobile) menu list; keep them in one place only
    nav: m.nav.filter((i) => !m.buttons.some((b) => b.label === i.label))
      .map((i) => ({ label: i.label, href: i.href || "", children: i.children })),
    utility_links: [],
    footer_columns: footerColumns,
    social: f?.social || [],
    contact: { address: addrLine ? [addrLine] : [], phones, emails },
    fonts: { body: bodyFont || null, heading: headingFont || null, stylesheets },
  };

  console.log("Measured tokens:");
  for (const [k, v] of Object.entries(css)) console.log(`  ${k}: ${v}`);
  console.log(`Menu: ${brand.nav.map((n) => n.label + (n.children.length ? ` (${n.children.length})` : "")).join(" | ")}`);
  console.log(`Header: note="${brand.header_note}" buttons=${brand.header_buttons.map((b) => b.label).join(", ")}`);
  console.log(`Contact: ${JSON.stringify(brand.contact)}`);
  console.log(`Assets: logo=${logoPath} banner=${bannerPath} favicon=${faviconPath}`);
  for (const line of report) console.log(`- ${line}`);
  if (DRY) return;

  const lines = ["/*", ` * Brand design tokens measured from the rendered pages of ${URL_BASE} on ${brand.measured_at}.`,
    " * Generated by scripts/measure_brand.mjs - re-run the script instead of editing by hand.",
    ...report.map((r) => ` * ${r}`), " */", ":root {"];
  // keep provisional values for anything not measured
  const previous = Object.fromEntries([...readFileSync(join(BRAND_DIR, "brand.css"), "utf8").matchAll(/(--brand-[\w-]+):\s*([^;]+);/g)].map((x) => [x[1], x[2]]));
  for (const [k, v] of Object.entries({ ...previous, ...css })) lines.push(`  ${k}: ${v};`);
  lines.push("}");
  writeFileSync(join(BRAND_DIR, "brand.css"), lines.join("\n") + "\n");
  writeFileSync(join(BRAND_DIR, "brand.json"), JSON.stringify(brand, null, 2) + "\n");
  console.log(`Wrote ${join(BRAND_DIR, "brand.json")} and brand.css`);
}

main().catch((err) => {
  console.error(err);
  process.exit(1);
});
