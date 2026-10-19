import { useEffect, useSyncExternalStore } from "react";
import { checkHealth } from "../api/client";
import { MIN_LOAD_MS, moments, momentForFailure } from "./moments";
import { Robot } from "./Robot";

/**
 * Arivazhai's moments: the robot pops up centred over a blurred screen for about 2.5 s, then
 * floats away. It never stays in the chat. On page load it shows "loading" while the assistant
 * is contacted, then "welcome" (or "offline"/"error" if it cannot be reached).
 */
export function RobotMoments() {
  const { moment, leaving } = useSyncExternalStore(moments.subscribe, moments.getSnapshot, moments.getSnapshot);

  useEffect(() => {
    const controller = new AbortController();
    moments.show({ kind: "load" }, { sticky: true });
    checkHealth(controller.signal).then((status) => {
      if (controller.signal.aborted) return;
      moments.showAfter(status === "ok" ? { kind: "greet" } : momentForFailure(status), MIN_LOAD_MS);
    });
    const offline = () => moments.show({ kind: "net" });
    const onKey = (event: KeyboardEvent) => {
      if (event.key === "Escape") moments.dismiss();
    };
    window.addEventListener("offline", offline);
    window.addEventListener("keydown", onKey);
    return () => {
      controller.abort();
      moments.dismiss();
      window.removeEventListener("offline", offline);
      window.removeEventListener("keydown", onKey);
    };
  }, []);

  return (
    <div className={`moment${moment ? " is-shown" : ""}${leaving ? " is-leaving" : ""}`} aria-live="polite">
      {moment && (
        <div className="mov" key={moment.id} data-moment={moment.kind}>
          <div className="moment__robot">
            <Robot moment={moment.kind} />
          </div>
          <p className="moment__title">{moment.title}</p>
          <p className="moment__text">{moment.text}</p>
        </div>
      )}
    </div>
  );
}
