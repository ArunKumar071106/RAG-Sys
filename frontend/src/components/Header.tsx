import { useEffect, useId, useRef, useState } from "react";
import { startChat } from "./ChatWindow";
import { brand, safeHref, type BrandLink } from "../brand";

function Logo() {
  if (brand.logo) {
    return <img className="brand-logo" src={brand.logo} alt={brand.logo_alt} />;
  }
  // No measured logo: a text monogram, never an invented emblem.
  return (
    <>
      <span className="brand-monogram" aria-hidden="true">
        {brand.short_name}
      </span>
      <span className="brandbar__name">{brand.college_name}</span>
    </>
  );
}

function MenuItem({ item }: { item: BrandLink }) {
  const [open, setOpen] = useState(false);
  const submenuId = useId();
  const ref = useRef<HTMLLIElement>(null);
  const children = (item.children ?? []).filter((c) => safeHref(c.href));

  useEffect(() => {
    if (!open) return;
    const close = (event: MouseEvent | KeyboardEvent) => {
      if (event instanceof KeyboardEvent ? event.key === "Escape" : !ref.current?.contains(event.target as Node)) setOpen(false);
    };
    document.addEventListener("mousedown", close);
    document.addEventListener("keydown", close);
    return () => {
      document.removeEventListener("mousedown", close);
      document.removeEventListener("keydown", close);
    };
  }, [open]);

  if (children.length === 0) {
    const href = safeHref(item.href);
    return href ? (
      <li>
        <a href={href}>{item.label}</a>
      </li>
    ) : null;
  }
  return (
    <li ref={ref} className={`has-submenu${open ? " is-open" : ""}`}>
      <button type="button" aria-expanded={open} aria-controls={submenuId} onClick={() => setOpen((o) => !o)}>
        {item.label}
        <span className="submenu-icon" aria-hidden="true" />
      </button>
      <ul id={submenuId} className="submenu">
        {children.map((child) => (
          <li key={child.label + child.href}>
            <a href={safeHref(child.href)}>{child.label}</a>
          </li>
        ))}
      </ul>
    </li>
  );
}

export function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navId = useId();
  const buttons = (brand.header_buttons ?? []).filter((b) => safeHref(b.href));

  return (
    <header className="site-header">
      {brand.header_note && (
        <p className="header-note header-note--mobile">
          <span>{brand.header_note}</span>
        </p>
      )}
      {brand.utility_links.length > 0 && (
        <div className="topbar">
          <ul className="container topbar__links" aria-label="Quick links">
            {brand.utility_links.map((link) => {
              const href = safeHref(link.href);
              return href ? (
                <li key={link.label}>
                  <a href={href}>{link.label}</a>
                </li>
              ) : null;
            })}
          </ul>
        </div>
      )}

      <div className="brandbar">
        <div className="container brandbar__inner">
          <a className="brandbar__home" href={safeHref(brand.official_url)} aria-label={`${brand.college_name} - official website home`}>
            <Logo />
          </a>
          {(brand.header_note || buttons.length > 0) && (
            <div className="brandbar__aside">
              {brand.header_note && <p className="header-note">{brand.header_note}</p>}
              {buttons.length > 0 && (
                <ul className="header-buttons" aria-label="Quick links">
                  {buttons.map((b) => (
                    <li key={b.label}>
                      <a className="pill" href={safeHref(b.href)}>
                        {b.label}
                      </a>
                    </li>
                  ))}
                </ul>
              )}
            </div>
          )}
          <button
            type="button"
            className="menu-toggle"
            aria-expanded={menuOpen}
            aria-controls={navId}
            onClick={() => setMenuOpen((open) => !open)}
          >
            <span className="menu-toggle__bars" aria-hidden="true" />
            <span className="visually-hidden">{menuOpen ? "Close menu" : "Open menu"}</span>
          </button>
        </div>
      </div>

      <nav className={`mainnav${menuOpen ? " mainnav--open" : ""}`} aria-label="Main">
        <ul id={navId} className="container mainnav__list">
          {brand.nav.map((item) => (
            <MenuItem key={item.label} item={item} />
          ))}
          <li>
            <a
              href="#assistant"
              aria-current="page"
              onClick={(event) => {
                event.preventDefault();
                setMenuOpen(false);
                startChat();
              }}
            >
              Arivazhai
            </a>
          </li>
          {buttons.map((b) => (
            <li key={`m-${b.label}`} className="mainnav__mobile-only">
              <a href={safeHref(b.href)}>{b.label}</a>
            </li>
          ))}
        </ul>
      </nav>
    </header>
  );
}
