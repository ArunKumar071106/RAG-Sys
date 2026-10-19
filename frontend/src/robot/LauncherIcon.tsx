import { memo, useId } from "react";
import "./robot.css";

interface Props {
  /** Blinking eyes, as in the design; off for the small static avatars in the conversation. */
  blink?: boolean;
}

/** Head-only launcher art from the design project (Icon.dc.html): used below 96 px, where the full body turns to noise. */
export const LauncherIcon = memo(function LauncherIcon({ blink = true }: Props) {
  const uid = `ic${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <svg className={blink ? "ic" : undefined} viewBox="22 0 196 160" width="80%" height="80%" aria-hidden="true" focusable="false">
      <defs>
      <radialGradient id={`${uid}Body`} cx="0.38" cy="0.28" r="0.85"><stop offset="0" stopColor="#FFFFFF" /><stop offset="0.6" stopColor="#EEF2F8" /><stop offset="1" stopColor="#C2CCDA" /></radialGradient>
      <linearGradient id={`${uid}Screen`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#1A2F66" /><stop offset="1" stopColor="#0A1430" /></linearGradient>
      </defs>
      <line x1="120" y1="36" x2="120" y2="18" stroke="#DCE3EE" strokeWidth="5" strokeLinecap="round" />
      <circle cx="120" cy="14" r="7" fill="#6CF0FF" />
      <circle cx="40" cy="96" r="15" fill="#DCE3EE" />
      <circle cx="200" cy="96" r="15" fill="#DCE3EE" />
      <rect x="40" y="34" width="160" height="120" rx="54" fill={`url(#${uid}Body)`} />
      <rect x="56" y="52" width="128" height="86" rx="38" fill={`url(#${uid}Screen)`} />
      <g className="eyes">
      <rect x="79" y="74" width="24" height="32" rx="12" fill="#6CF0FF" />
      <rect x="137" y="74" width="24" height="32" rx="12" fill="#6CF0FF" />
      <circle cx="96" cy="83" r="5" fill="#FFFFFF" />
      <circle cx="154" cy="83" r="5" fill="#FFFFFF" />
      </g>
      <ellipse cx="72" cy="120" rx="9" ry="6" fill="#FF8FC0" opacity="0.5" />
      <ellipse cx="168" cy="120" rx="9" ry="6" fill="#FF8FC0" opacity="0.5" />
      <path d="M102 115 Q120 140 138 115 Q120 122 102 115 Z" fill="#9FF7FF" />
    </svg>
  );
});
