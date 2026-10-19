import { Robot } from "./Robot";

/** Arivazhai's profile picture: the robot's face from the design, in a gold-ringed disc. */
export function RobotProfile({ size = "large" }: { size?: "large" | "small" }) {
  return (
    <span className={`profile profile--${size}`} aria-hidden="true">
      <Robot crop="head" />
    </span>
  );
}
