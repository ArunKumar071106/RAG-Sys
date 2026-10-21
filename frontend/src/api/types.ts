// Mirrors the FastAPI response models in backend/rag/llm/answer.py.

export interface ChatTurn {
  role: "user" | "assistant";
  content: string;
}

export interface Source {
  id: string;
  chunk_id: string;
  title: string;
  url: string;
  heading: string;
  snippet: string;
  score: number;
}

export interface ChatImage {
  id: string;
  image_id: string;
  src: string;
  original_url: string;
  source_page: string;
  page_title: string;
  heading: string;
  alt: string;
  caption: string;
  ocr_text: string;
  description: string;
  description_is_ai_generated: boolean;
  width: number;
  height: number;
}

export interface ChatResult {
  answer: string;
  mode: "llm" | "extractive" | "no_answer";
  insufficient_evidence: boolean;
  sources: Source[];
  related_sources: Source[];
  images: ChatImage[];
  notice: string;
  model: string;
  timings_ms: Record<string, number>;
  /** Not in English and an AI service is set up: an English version can be asked for. */
  translatable?: boolean;
  /** Full questions to offer next, about the same department or related topics. */
  follow_ups?: string[];
}
