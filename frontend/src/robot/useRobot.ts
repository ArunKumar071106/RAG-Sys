import { useEffect, useState, useSyncExternalStore } from "react";
import { RobotDirector, type RobotSnapshot } from "./states";

/** A director that lives as long as the component that owns it. */
export function useRobotDirector(): RobotDirector {
  const [director] = useState(() => new RobotDirector());
  useEffect(() => () => director.dispose(), [director]);
  return director;
}

/** The robot's current state and caption; re-renders only when they change. */
export function useRobot(director: RobotDirector): RobotSnapshot {
  return useSyncExternalStore(director.subscribe, director.getSnapshot, director.getSnapshot);
}
