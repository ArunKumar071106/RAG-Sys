import { LauncherIcon } from "./LauncherIcon";

/** The assistant's avatar next to its messages: the launcher's head-only art, without blinking. */
export function RobotAvatar() {
  return (
    <div className="avatar avatar--robot" aria-hidden="true">
      <LauncherIcon blink={false} />
    </div>
  );
}
