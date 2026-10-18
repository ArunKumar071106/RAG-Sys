import type { ChatImage, Source } from "../api/types";

const escapeTitle = (text: string) => text.replace(/["\\]/g, "\\$&").replace(/[\r\n]+/g, " ");

/**
 * Turn the backend's citation markers into Markdown links:
 *   [S2] -> [[2]](https://official/page "Source 2: Page title")
 *   [I1] -> [[image 1]](#<prefix>-I1)          (jumps to the image card)
 * Unknown markers are removed rather than rendered as dead links.
 */
export function linkCitations(answer: string, sources: Source[], images: ChatImage[], anchorPrefix: string): string {
  const byId = new Map(sources.map((s) => [s.id, s]));
  const imageIds = new Set(images.map((i) => i.id));
  return answer.replace(/\[(S|I)(\d+)\]/g, (_match, kind: string, num: string) => {
    if (kind === "S") {
      const source = byId.get(`S${num}`);
      return source ? `[[${num}]](${source.url} "Source ${num}: ${escapeTitle(source.title)}")` : "";
    }
    return imageIds.has(`I${num}`) ? `[[image ${num}]](#${anchorPrefix}-I${num})` : "";
  });
}

export const CITATION_TEXT = /^\[(\d+|image \d+)\]$/;
