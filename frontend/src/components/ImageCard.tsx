import { useState } from "react";
import { apiUrl } from "../api/client";
import type { ChatImage } from "../api/types";
import { safeHref } from "../brand";

interface Props {
  image: ChatImage;
  index: number;
  anchorId?: string;
}

type Stage = "local" | "original" | "failed";

export function ImageCard({ image, index, anchorId }: Props) {
  // Try the copy served by our API first, then the original URL, then a placeholder.
  const [stage, setStage] = useState<Stage>("local");
  const src = stage === "local" ? apiUrl(image.src) : image.original_url;
  const alt = image.alt || image.caption || `Image from the page "${image.page_title}"`;
  const pageHref = safeHref(image.source_page);
  const originalHref = safeHref(image.original_url);

  return (
    <figure className="image-card" id={anchorId}>
      <div className="image-card__frame" style={image.width && image.height ? { aspectRatio: `${image.width} / ${image.height}` } : undefined}>
        {stage !== "failed" ? (
          <img
            src={src}
            alt={alt}
            loading="lazy"
            decoding="async"
            onError={() => setStage((s) => (s === "local" && originalHref ? "original" : "failed"))}
          />
        ) : (
          <div className="image-card__missing" role="img" aria-label={`Image unavailable: ${alt}`}>
            <svg viewBox="0 0 24 24" width="28" height="28" aria-hidden="true" focusable="false">
              <path fill="currentColor" d="M21 5v14H3V5h18m0-2H3a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h18a2 2 0 0 0 2-2V5a2 2 0 0 0-2-2zm-7.5 9.5-3 3.9-2-2.6L5.5 17h13l-5-4.5z" />
            </svg>
            <span>Image unavailable</span>
          </div>
        )}
        <span className="image-card__badge">Image {index}</span>
      </div>
      <figcaption className="image-card__caption">
        <span className="image-card__title">{image.caption || image.alt || image.page_title}</span>
        {image.heading && <span className="image-card__meta">{image.page_title} - {image.heading}</span>}
        {image.ocr_text && (
          <details className="image-card__details">
            <summary>Text in image (OCR)</summary>
            <p className="image-card__ocr">{image.ocr_text}</p>
          </details>
        )}
        {image.description_is_ai_generated && image.description && (
          <p className="image-card__ai">
            <span className="tag tag--ai">AI-generated description</span> {image.description}
          </p>
        )}
        <span className="image-card__links">
          {pageHref && (
            <a href={pageHref} target="_blank" rel="noopener noreferrer">
              View source page<span className="visually-hidden"> (opens in a new tab)</span>
            </a>
          )}
          {originalHref && (
            <a href={originalHref} target="_blank" rel="noopener noreferrer">
              Open image<span className="visually-hidden"> (opens in a new tab)</span>
            </a>
          )}
        </span>
      </figcaption>
    </figure>
  );
}
