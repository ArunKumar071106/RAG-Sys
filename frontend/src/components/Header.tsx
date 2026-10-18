import { useId, useState } from "react";
import { brand, safeHref } from "../brand";

function Logo() {
  if (brand.logo) {
    return <img className="brand-logo" src={brand.logo} alt={brand.logo_alt} />;
  }
  // No measured logo yet: a text monogram, not an invented emblem.
  return (
    <span className="brand-monogram" aria-hidden="true">
      {brand.short_name}
    </span>
  );
}

export function Header() {
  const [menuOpen, setMenuOpen] = useState(false);
  const navId = useId();
  const { contact } = brand;

  return (
    <header className="site-header">
      <div className="topbar">
        <div className="container topbar__inner">
          <ul className="topbar__contact" aria-label="Contact">
            {contact.phones.slice(0, 2).map((phone) => (
              <li key={phone}>
                <a href={`tel:${phone.replace(/[^\d+]/g, "")}`}>{phone}</a>
              </li>
            ))}
            {contact.emails.slice(0, 1).map((email) => (
              <li key={email}>
                <a href={`mailto:${email}`}>{email}</a>
              </li>
            ))}
          </ul>
          <ul className="topbar__links" aria-label="Quick links">
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
      </div>

      <div className="brandbar">
        <div className="container brandbar__inner">
          <a className="brandbar__home" href={safeHref(brand.official_url)} aria-label={`${brand.college_name} - official website home`}>
            <Logo />
            <span className="brandbar__text">
              <span className="brandbar__name">{brand.college_name}</span>
              {brand.tagline && <span className="brandbar__tagline">{brand.tagline}</span>}
            </span>
          </a>
          {brand.badges.length > 0 && (
            <ul className="brandbar__badges" aria-label="Accreditations">
              {brand.badges.map((badge) => (
                <li key={badge.src}>
                  <img src={badge.src} alt={badge.alt} />
                </li>
              ))}
            </ul>
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
          {brand.nav.map((item) => {
            const href = safeHref(item.href);
            return href ? (
              <li key={item.label}>
                <a href={href}>{item.label}</a>
              </li>
            ) : null;
          })}
          <li>
            <a href="#assistant" aria-current="page">
              Virtual Assistant
            </a>
          </li>
        </ul>
      </nav>
    </header>
  );
}
