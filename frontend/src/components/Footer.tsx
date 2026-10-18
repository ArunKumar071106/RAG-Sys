import { brand, safeHref } from "../brand";

export function Footer() {
  const { contact } = brand;
  const officialHost = (() => {
    try {
      return new URL(brand.official_url).host;
    } catch {
      return brand.official_url;
    }
  })();

  return (
    <footer className="site-footer">
      <div className="container site-footer__grid">
        <section aria-labelledby="footer-college">
          <h2 id="footer-college" className="site-footer__heading">
            {brand.college_name}
          </h2>
          {contact.address.length > 0 && (
            <address>
              {contact.address.map((line) => (
                <span key={line} className="site-footer__line">
                  {line}
                </span>
              ))}
            </address>
          )}
          {contact.phones.length > 0 && <p>Phone: {contact.phones.join(", ")}</p>}
          {contact.emails.length > 0 && <p>Email: {contact.emails.join(", ")}</p>}
        </section>
        <section aria-labelledby="footer-links">
          <h2 id="footer-links" className="site-footer__heading">
            Quick Links
          </h2>
          <ul className="site-footer__links">
            {[...brand.nav, ...brand.utility_links]
              .filter((link, i, all) => all.findIndex((l) => l.label === link.label) === i)
              .map((link) => {
                const href = safeHref(link.href);
                return href ? (
                  <li key={link.label}>
                    <a href={href}>{link.label}</a>
                  </li>
                ) : null;
              })}
          </ul>
        </section>
        <section aria-labelledby="footer-about">
          <h2 id="footer-about" className="site-footer__heading">
            About this assistant
          </h2>
          <p>
            Answers are generated from content published on the official website. Please confirm important details such as fees and
            deadlines with the college office.
          </p>
        </section>
      </div>
      <div className="site-footer__bottom">
        <div className="container">
          Official website: <a href={safeHref(brand.official_url)}>{officialHost}</a>
        </div>
      </div>
    </footer>
  );
}
