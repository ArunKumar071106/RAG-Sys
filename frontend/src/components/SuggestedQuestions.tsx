import { useId } from "react";

// Worded the way the website words things; each is in backend/eval/questions_aaacet.jsonl,
// so `make eval` checks it against the real knowledge base.
export const DEFAULT_SUGGESTIONS = [
  "What is the intake for each B.E. and B.Tech course?",
  "How do I apply for admission?",
  "Tell me about placements and recruiters",
  "What hostel facilities are available?",
  "Show me photos of the campus library",
  "What is the contact phone number and email of the college?",
];

interface Props {
  questions?: string[];
  onSelect: (question: string) => void;
  disabled?: boolean;
  title?: string;
}

export function SuggestedQuestions({ questions = DEFAULT_SUGGESTIONS, onSelect, disabled, title = "Try asking" }: Props) {
  const titleId = useId();
  return (
    <div className="suggestions">
      <h3 className="suggestions__title" id={titleId}>
        {title}
      </h3>
      <ul className="suggestions__list" aria-labelledby={titleId}>
        {questions.map((q) => (
          <li key={q}>
            <button type="button" className="chip" onClick={() => onSelect(q)} disabled={disabled}>
              {q}
            </button>
          </li>
        ))}
      </ul>
    </div>
  );
}
