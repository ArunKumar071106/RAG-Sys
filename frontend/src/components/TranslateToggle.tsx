import { useRef, useState } from "react";
import { ApiError, translateAnswer } from "../api/client";

interface Props {
  text: string;
  /** Shows the English version (or the original again) in place of the answer. */
  onShow: (english: string | null) => void;
}

/** "Show in English" for an answer given in another language; "Show original" switches back. */
export function TranslateToggle({ text, onShow }: Props) {
  const [english, setEnglish] = useState<string | null>(null);
  const [showing, setShowing] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const controller = useRef<AbortController | null>(null);

  const toggle = async () => {
    if (showing) {
      setShowing(false);
      onShow(null);
      return;
    }
    if (english) {
      setShowing(true);
      onShow(english);
      return;
    }
    controller.current?.abort();
    controller.current = new AbortController();
    setBusy(true);
    setError("");
    try {
      const translated = await translateAnswer(text, controller.current.signal);
      setEnglish(translated);
      setShowing(true);
      onShow(translated);
    } catch (err) {
      setError(err instanceof ApiError ? err.message : "The English version is not available right now.");
    } finally {
      setBusy(false);
    }
  };

  return (
    <div className="translate">
      <button type="button" className="translate__button" onClick={toggle} disabled={busy} aria-pressed={showing}>
        <span aria-hidden="true">🌐</span> {busy ? "Translating…" : showing ? "Show original" : "Show in English"}
      </button>
      {error && (
        <span className="translate__error" role="alert">
          {error}
        </span>
      )}
    </div>
  );
}
