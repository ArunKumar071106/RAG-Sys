import { brand, safeHref } from "../brand";

const ICONS: Record<string, string> = {
  address: "M12 2a7 7 0 0 0-7 7c0 5.25 7 13 7 13s7-7.75 7-13a7 7 0 0 0-7-7zm0 9.5A2.5 2.5 0 1 1 12 6.5a2.5 2.5 0 0 1 0 5z",
  email: "M20 4H4a2 2 0 0 0-2 2v12a2 2 0 0 0 2 2h16a2 2 0 0 0 2-2V6a2 2 0 0 0-2-2zm0 4-8 5-8-5V6l8 5 8-5z",
  phone: "M6.6 10.8a15.1 15.1 0 0 0 6.6 6.6l2.2-2.2a1 1 0 0 1 1-.25 11.4 11.4 0 0 0 3.6.57 1 1 0 0 1 1 1V20a1 1 0 0 1-1 1A17 17 0 0 1 3 4a1 1 0 0 1 1-1h3.5a1 1 0 0 1 1 1c0 1.25.2 2.45.57 3.6a1 1 0 0 1-.25 1z",
};

function Icon({ name }: { name: keyof typeof ICONS }) {
  return (
    <svg className="site-footer__icon" viewBox="0 0 24 24" width="18" height="18" aria-hidden="true" focusable="false">
      <path fill="currentColor" d={ICONS[name]} />
    </svg>
  );
}

export function Footer() {
  const { contact } = brand;
  const columns = brand.footer_columns?.length
    ? brand.footer_columns
    : [{ title: "Quick Links", links: [...brand.nav, ...brand.utility_links].filter((l) => safeHref(l.href)) }];
  const officialHost = (() => {
    try {
      return new URL(brand.official_url).host;
    } catch {
      return brand.official_url;
    }
  })();
  const hasContact = contact.address.length + contact.phones.length + contact.emails.length > 0;

  return (
    <footer className="site-footer">
      <div className="container site-footer__grid">
        <section aria-labelledby="footer-about">
          <h2 id="footer-about" className="site-footer__heading">
            About Arivazhai
          </h2>
          <p>
            Arivazhai, the {brand.short_name} admission assistant, answers from content published on the official {brand.college_name} website.
            Please confirm important details such as fees and deadlines with the college office.
          </p>
        </section>
        {columns.map((column, i) => (
          <section key={column.title} aria-labelledby={`footer-col-${i}`}>
            <h2 id={`footer-col-${i}`} className="site-footer__heading">
              {column.title}
            </h2>
            <ul className="site-footer__links">
              {column.links.map((link) => {
                const href = safeHref(link.href);
                return href ? (
                  <li key={link.label + href}>
                    <a href={href}>{link.label}</a>
                  </li>
                ) : null;
              })}
            </ul>
          </section>
        ))}
        {hasContact && (
          <section aria-labelledby="footer-contact">
            <h2 id="footer-contact" className="site-footer__heading">
              Contact
            </h2>
            <ul className="site-footer__contact">
              {contact.address.length > 0 && (
                <li>
                  <Icon name="address" />
                  <address>{contact.address.join(", ")}</address>
                </li>
              )}
              {contact.emails.map((email) => (
                <li key={email}>
                  <Icon name="email" />
                  <a href={`mailto:${email}`}>{email}</a>
                </li>
              ))}
              {contact.phones.length > 0 && (
                <li>
                  <Icon name="phone" />
                  <span>
                    {contact.phones.map((phone, i) => (
                      <span key={phone}>
                        {i > 0 && ", "}
                        <a href={`tel:${phone.replace(/[^\d+]/g, "")}`}>{phone}</a>
                      </span>
                    ))}
                  </span>
                </li>
              )}
            </ul>
            {(brand.social ?? []).length > 0 && (
              <ul className="site-footer__social" aria-label="Social media">
                {(brand.social ?? []).map((s) => {
                  const href = safeHref(s.href);
                  return href ? (
                    <li key={href}>
                      <a href={href} target="_blank" rel="noopener noreferrer">
                        {s.label}
                      </a>
                    </li>
                  ) : null;
                })}
              </ul>
            )}
          </section>
        )}
      </div>
      <div className="site-footer__bottom">
        <div className="container">
          Official website: <a href={safeHref(brand.official_url)}>{officialHost}</a>
        </div>
      </div>
    </footer>
  );
}
