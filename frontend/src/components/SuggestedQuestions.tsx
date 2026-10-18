export const DEFAULT_SUGGESTIONS = [
  "What courses does AAACET offer?",
  "How do I apply for admission?",
  "Tell me about placements and recruiters",
  "What hostel facilities are available?",
  "Show me photos of the campus library",
  "How can I contact the college office?",
];

interface Props {
  questions?: string[];
  onSelect: (question: string) => void;
  disabled?: boolean;
}

export function SuggestedQuestions({ questions = DEFAULT_SUGGESTIONS, onSelect, disabled }: Props) {
  return (
    <div className="suggestions">
      <h3 className="suggestions__title" id="suggestions-title">
        Try asking
      </h3>
      <ul className="suggestions__list" aria-labelledby="suggestions-title">
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
