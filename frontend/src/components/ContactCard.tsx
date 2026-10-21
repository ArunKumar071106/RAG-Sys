import { brand } from "../brand";

/** "18004258807" -> "1800 425 8807"; other numbers as the website writes them. */
export function formatPhone(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  return /^1800\d{7}$/.test(digits) ? `${digits.slice(0, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}` : phone;
}

const telHref = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;

/** The college office's phone numbers and email from the official website, as tap-to-call links. */
export function ContactCard({ title = "Contact the admission office" }: { title?: string }) {
  const { phones, emails } = brand.contact;
  if (phones.length === 0 && emails.length === 0) return null;
  return (
    <section className="contact-card" aria-label={title}>
      <h4 className="contact-card__title">{title}</h4>
      <ul className="contact-card__list">
        {phones.map((phone) => (
          <li key={phone}>
            <span aria-hidden="true">📞</span>{" "}
            <a href={telHref(phone)}>{formatPhone(phone)}</a>
            {/^1800/.test(phone.replace(/\D/g, "")) && <span className="contact-card__note"> (toll-free)</span>}
          </li>
        ))}
        {emails.map((email) => (
          <li key={email}>
            <span aria-hidden="true">✉️</span> <a href={`mailto:${email}`}>{email}</a>
          </li>
        ))}
      </ul>
    </section>
  );
}

/** Questions where the answer should end with the ways to reach the college. */
export const CONTACT_QUESTION = /\b(contact|phone|call|mobile|number|e-?mail|mail|enquir|inquir|reach|address|helpline|office)/i;
