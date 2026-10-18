import type { Source } from "../api/types";
import { safeHref } from "../brand";

interface Props {
  sources: Source[];
  title?: string;
  variant?: "cited" | "related";
}

export function SourceList({ sources, title = "Sources from the official website", variant = "cited" }: Props) {
  if (!sources.length) return null;
  return (
    <section className={`sources sources--${variant}`} aria-label={title}>
      <h4 className="sources__title">{title}</h4>
      <ol className="sources__list">
        {sources.map((source, index) => {
          const href = safeHref(source.url);
          return (
            <li key={source.chunk_id} className="sources__item">
              {variant === "cited" && <span className="sources__num" aria-hidden="true">{index + 1}</span>}
              <div className="sources__body">
                {href ? (
                  <a href={href} target="_blank" rel="noopener noreferrer" className="sources__link">
                    {source.title}
                    {source.heading && <span className="sources__heading"> - {source.heading}</span>}
                    <span className="visually-hidden"> (opens official page in a new tab)</span>
                  </a>
                ) : (
                  <span className="sources__link">{source.title}</span>
                )}
                {source.snippet && <p className="sources__snippet">{source.snippet}</p>}
              </div>
            </li>
          );
        })}
      </ol>
    </section>
  );
}
