import { brand } from "../brand";
import contacts from "../brand/contacts.json";

interface Person {
  name: string;
  role?: string;
  phone: string;
}

/** "18004258807" -> "1800 425 8807"; other numbers as the website writes them. */
export function formatPhone(phone: string): string {
  const digits = phone.replace(/\D/g, "");
  return /^1800\d{7}$/.test(digits) ? `${digits.slice(0, 4)} ${digits.slice(4, 7)} ${digits.slice(7)}` : phone;
}

const telHref = (phone: string) => `tel:${phone.replace(/[^\d+]/g, "")}`;
const unique = (items: string[]) => [...new Map(items.map((x) => [x.replace(/\D/g, "") || x.toLowerCase(), x])).values()];

/** The office numbers and emails of the website's footer and contact page, plus the admission and scholarship staff. */
export const officePhones = unique([...contacts.office_phones, ...brand.contact.phones]);
export const officeEmails = unique([...contacts.emails, ...brand.contact.emails]);
export const admissionStaff: Person[] = contacts.admission;

/**
 * How to reach the college, as tap-to-call and email links: the office numbers and emails, and
 * for admission questions the admission and scholarship staff listed on the admission page.
 */
export function ContactCard({ title = "Contact the admission office", staff = false }: { title?: string; staff?: boolean }) {
  if (officePhones.length === 0 && officeEmails.length === 0) return null;
  return (
    <section className="contact-card" aria-label={title}>
      <h4 className="contact-card__title">{title}</h4>
      <ul className="contact-card__list">
        {officePhones.map((phone) => (
          <li key={phone}>
            <span aria-hidden="true">📞</span>{" "}
            <a href={telHref(phone)}>{formatPhone(phone)}</a>
            {/^1800/.test(phone.replace(/\D/g, "")) && <span className="contact-card__note"> (toll-free)</span>}
          </li>
        ))}
        {officeEmails.map((email) => (
          <li key={email}>
            <span aria-hidden="true">✉️</span> <a href={`mailto:${email}`}>{email}</a>
          </li>
        ))}
      </ul>
      {staff && admissionStaff.length > 0 && (
        <>
          <h5 className="contact-card__subtitle">Admission &amp; scholarship</h5>
          <ul className="contact-card__people">
            {admissionStaff.map((person) => (
              <li key={person.phone}>
                <span className="contact-card__name">
                  {person.name}
                  {person.role && <span className="contact-card__role">{person.role}</span>}
                </span>{" "}
                <a href={telHref(person.phone)}>{person.phone}</a>
              </li>
            ))}
          </ul>
        </>
      )}
    </section>
  );
}

/** Questions where the answer should end with the ways to reach the college. */
export const CONTACT_QUESTION = /\b(contact|phone|call|mobile|number|e-?mail|mail|enquir|inquir|reach|address|helpline|office)/i;
/** Questions the admission and scholarship staff answer. */
export const ADMISSION_QUESTION = /\b(admission|admit|apply|application|counsell?ing|scholarship|fees?|quota|seat|eligib|join)/i;
