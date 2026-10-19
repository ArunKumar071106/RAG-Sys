import { RobotProfile } from "../robot/RobotProfile";

/** Who is speaking, above each assistant message: Arivazhai's profile picture and name. */
export function AssistantLabel() {
  return (
    <span className="message__sender" aria-hidden="true">
      <RobotProfile size="small" />
      Arivazhai
    </span>
  );
}
