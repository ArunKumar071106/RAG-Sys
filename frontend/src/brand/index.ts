import raw from "./brand.json";

export interface BrandLink {
  label: string;
  href: string;
  children?: BrandLink[];
}

export interface Brand {
  measured: boolean;
  source: string;
  measured_at: string | null;
  college_name: string;
  short_name: string;
  tagline: string;
  official_url: string;
  logo: string | null;
  logo_alt: string;
  favicon?: string | null;
  banner_image?: string | null;
  header_note?: string;
  header_buttons?: BrandLink[];
  badges: { src: string; alt: string }[];
  nav: BrandLink[];
  utility_links: BrandLink[];
  footer_columns?: { title: string; links: BrandLink[] }[];
  social?: BrandLink[];
  contact: { address: string[]; phones: string[]; emails: string[] };
  fonts: { body: string | null; heading: string | null; stylesheets: string[] };
}

export const brand = raw as unknown as Brand;

/** Only http(s) links from the brand file are rendered. */
export function safeHref(href: string): string | undefined {
  if (!href) return undefined;
  try {
    const url = new URL(href, brand.official_url);
    return url.protocol === "http:" || url.protocol === "https:" ? url.toString() : undefined;
  } catch {
    return undefined;
  }
}

export function loadBrandFonts(doc: Document = document): void {
  for (const href of brand.fonts.stylesheets) {
    if (!/^https:\/\/fonts\.(googleapis|gstatic)\.com\//.test(href)) continue;
    if (doc.querySelector(`link[href="${CSS.escape(href)}"]`)) continue;
    const link = doc.createElement("link");
    link.rel = "stylesheet";
    link.href = href;
    doc.head.appendChild(link);
  }
  if (brand.favicon) {
    const icon = doc.querySelector<HTMLLinkElement>("link[rel~='icon']") ?? doc.head.appendChild(doc.createElement("link"));
    icon.rel = "icon";
    icon.href = brand.favicon;
  }
}
