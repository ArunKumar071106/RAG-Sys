import { useId } from "react";

// What parents ask most before admission, worded the way the website words things. Each is in
// backend/eval/questions_aaacet.jsonl, so `make eval` checks it against the real knowledge base.
export const DEFAULT_SUGGESTIONS = [
  "What is the eligibility for B.E. / B.Tech admission?",
  "What is the TNEA counselling code of AAACET?",
  "How many seats are there in each department?",
  "How do I apply for admission online?",
  "What documents are needed for admission?",
  "What scholarships are available based on +2 cut-off marks?",
  "Are hostels available for boys and girls?",
  "Whom should I contact for admission?",
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
