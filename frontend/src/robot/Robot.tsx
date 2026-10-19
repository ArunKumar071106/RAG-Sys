import { memo, useId } from "react";
import type { RobotState } from "./states";
import "./robot.css";

export const DEFAULT_ACCENT = "#1F5BFF";

/** Screen-reader descriptions, worded as in the design's States.dc.html. */
export const ROBOT_ALT: Record<RobotState, string> = {
  idle: "Arivazhai floating with a gentle sway",
  greet: "Arivazhai hopping and waving with happy eyes",
  attend: "Arivazhai leaning in with a small wave",
  support: "Arivazhai reaching toward the chat with glowing hands",
  think: "Arivazhai scanning while particles orbit its head",
  answer: "Arivazhai bouncing happily with sparkles",
  confirm: "Arivazhai jumping with star eyes and a checkmark",
  unsure: "Arivazhai scratching its head with a question mark",
  error: "Arivazhai dimmed with a drooping antenna",
};

interface Props {
  state: RobotState;
  accent?: string;
  className?: string;
  /** Decorative copies (the state is also told in text nearby) are hidden from screen readers. */
  decorative?: boolean;
}

/**
 * The full-body Arivazhai rig from the design project (States.dc.html), unchanged: one SVG whose
 * state class switches expressions and motion through robot.css. Gradient ids are made unique per
 * instance so several robots (or a hidden one) can share a page.
 */
export const Robot = memo(function Robot({ state, accent = DEFAULT_ACCENT, className, decorative }: Props) {
  const uid = `rb${useId().replace(/[^a-zA-Z0-9]/g, "")}`;
  return (
    <svg
      className={`rb ${state}${className ? ` ${className}` : ""}`}
      viewBox="0 0 240 260"
      width="100%"
      height="100%"
      data-state={state}
      {...(decorative ? { "aria-hidden": true } : { role: "img", "aria-label": ROBOT_ALT[state] })}
    >
      <defs>
      <radialGradient id={`${uid}Body`} cx="0.36" cy="0.26" r="0.9"><stop offset="0" stopColor="#FFFFFF" /><stop offset="0.5" stopColor="#EEF2F8" /><stop offset="0.85" stopColor="#C5CFDD" /><stop offset="1" stopColor="#9AA9BF" /></radialGradient>
      <radialGradient id={`${uid}Silver`} cx="0.35" cy="0.3" r="0.8"><stop offset="0" stopColor="#FFFFFF" /><stop offset="1" stopColor="#A3B1C6" /></radialGradient>
      <radialGradient id={`${uid}Screen`} cx="0.5" cy="0.35" r="0.75"><stop offset="0" stopColor="#1E3B7C" /><stop offset="1" stopColor="#070F27" /></radialGradient>
      <linearGradient id={`${uid}Eye`} x1="0" y1="0" x2="0" y2="1"><stop offset="0" stopColor="#D6FEFF" /><stop offset="0.45" stopColor="#6CF0FF" /><stop offset="1" stopColor="#1FB8E6" /></linearGradient>
      <radialGradient id={`${uid}Glow`} cx="0.5" cy="0.5" r="0.5"><stop offset="0" stopColor="#6CF0FF" stopOpacity="0.85" /><stop offset="1" stopColor="#6CF0FF" stopOpacity="0" /></radialGradient>
      <radialGradient id={`${uid}PadG`} cx="0.5" cy="0.5" r="0.5"><stop offset="0" stopColor="#6CF0FF" stopOpacity="0.6" /><stop offset="0.6" stopColor="#3FA9FF" stopOpacity="0.18" /><stop offset="1" stopColor="#3FA9FF" stopOpacity="0" /></radialGradient>
      <filter id={`${uid}Blur`} x="-60%" y="-60%" width="220%" height="220%"><feGaussianBlur stdDeviation="3.2" /></filter>
      </defs>
      <ellipse className="pad" cx="120" cy="250" rx="58" ry="10" fill={`url(#${uid}PadG)`} />
      <g className="float">
      <g className="squash">
      <path className="ring ring-dash" d="M48 200 A72 15 0 0 1 192 200" fill="none" stroke="#6CF0FF" strokeWidth="2" strokeOpacity="0.4" strokeDasharray="5 7" strokeLinecap="round" />
      <rect x="106" y="150" width="28" height="12" rx="6" fill="#A3B1C6" />
      <path d="M70 182 C70 152 170 152 170 182 C170 218 148 240 120 240 C92 240 70 218 70 182 Z" fill={`url(#${uid}Body)`} />
      <path d="M160 174 C167 192 161 216 141 232" fill="none" stroke="#8FF4FF" strokeWidth="2.5" strokeLinecap="round" opacity="0.6" />
      <ellipse cx="120" cy="198" rx="30" ry="26" fill="#FFFFFF" opacity="0.5" />
      <path d="M84 170 Q120 162 156 170" fill="none" stroke="#C5CFDD" strokeWidth="1.5" strokeLinecap="round" />
      <circle className="core-glow" cx="120" cy="192" r="22" fill={`url(#${uid}Glow)`} />
      <circle cx="120" cy="192" r="12" fill="#0D1B3D" stroke={accent} strokeWidth="2.5" />
      <g className="core-spin">
      <path d="M120 184 A8 8 0 0 1 128 192" fill="none" stroke="#6CF0FF" strokeWidth="2" strokeLinecap="round" />
      <path d="M120 200 A8 8 0 0 1 112 192" fill="none" stroke="#6CF0FF" strokeWidth="2" strokeLinecap="round" />
      </g>
      <circle className="core" cx="120" cy="192" r="4.5" fill="#6CF0FF" />
      <g className="fx fx-core"><circle className="wave" cx="120" cy="192" r="26" fill="none" stroke="#6CF0FF" strokeWidth="2.5" /></g>
      <path className="ring ring-dash" d="M48 200 A72 15 0 0 0 192 200" fill="none" stroke="#6CF0FF" strokeWidth="2.2" strokeOpacity="0.8" strokeDasharray="5 7" strokeLinecap="round" />
      <g className="hand hand-l">
      <circle className="hglow" cx="44" cy="188" r="26" fill={`url(#${uid}Glow)`} />
      <ellipse cx="44" cy="188" rx="12.5" ry="15.5" fill={`url(#${uid}Silver)`} transform="rotate(-14 44 188)" />
      <ellipse cx="40" cy="182" rx="4" ry="6" fill="#FFFFFF" opacity="0.8" transform="rotate(-14 40 182)" />
      <ellipse cx="46" cy="198" rx="7" ry="3" fill={accent} opacity="0.9" transform="rotate(-14 46 198)" />
      </g>
      <g className="hand hand-r">
      <circle className="hglow" cx="196" cy="188" r="26" fill={`url(#${uid}Glow)`} />
      <ellipse cx="196" cy="188" rx="12.5" ry="15.5" fill={`url(#${uid}Silver)`} transform="rotate(14 196 188)" />
      <ellipse cx="192" cy="182" rx="4" ry="6" fill="#FFFFFF" opacity="0.8" transform="rotate(14 192 182)" />
      <ellipse cx="194" cy="198" rx="7" ry="3" fill={accent} opacity="0.9" transform="rotate(14 194 198)" />
      </g>
      <g className="hfollow">
      <g className="head">
      <g className="antenna">
      <path d="M120 38 Q117 28 121 20" fill="none" stroke="#A3B1C6" strokeWidth="4" strokeLinecap="round" />
      <circle className="tip" cx="121" cy="16" r="13" fill={`url(#${uid}Glow)`} />
      <circle cx="121" cy="16" r="6" fill={`url(#${uid}Eye)`} stroke={accent} strokeWidth="1.5" />
      </g>
      <circle cx="38" cy="96" r="15" fill={`url(#${uid}Silver)`} />
      <circle cx="38" cy="96" r="9" fill="none" stroke={accent} strokeWidth="3" />
      <circle className="ear-light" cx="38" cy="96" r="4" fill="#6CF0FF" />
      <circle cx="202" cy="96" r="15" fill={`url(#${uid}Silver)`} />
      <circle cx="202" cy="96" r="9" fill="none" stroke={accent} strokeWidth="3" />
      <circle className="ear-light" cx="202" cy="96" r="4" fill="#6CF0FF" />
      <rect x="38" y="34" width="164" height="122" rx="56" fill={`url(#${uid}Body)`} />
      <path d="M190 62 Q206 96 188 140" fill="none" stroke="#8FF4FF" strokeWidth="3" strokeLinecap="round" opacity="0.55" />
      <ellipse cx="84" cy="48" rx="28" ry="8" fill="#FFFFFF" opacity="0.95" transform="rotate(-10 84 48)" />
      <rect x="54" y="52" width="132" height="88" rx="40" fill={`url(#${uid}Screen)`} />
      <rect x="54" y="52" width="132" height="88" rx="40" fill="none" stroke="#6CF0FF" strokeWidth="1.5" opacity="0.2" />
      <path d="M68 84 Q74 62 104 59" fill="none" stroke="#FFFFFF" strokeWidth="6" strokeLinecap="round" opacity="0.13" />
      <g className="gaze">
      <g className="look">
      <g className="e-open" filter={`url(#${uid}Blur)`} opacity="0.75">
      <rect x="80" y="76" width="24" height="32" rx="12" fill="#6CF0FF" />
      <rect x="136" y="76" width="24" height="32" rx="12" fill="#6CF0FF" />
      </g>
      <g className="eyes e-open">
      <rect x="80" y="76" width="24" height="32" rx="12" fill={`url(#${uid}Eye)`} />
      <rect className="eye-r" x="136" y="76" width="24" height="32" rx="12" fill={`url(#${uid}Eye)`} />
      <circle cx="97" cy="85" r="4.5" fill="#FFFFFF" />
      <circle cx="153" cy="85" r="4.5" fill="#FFFFFF" />
      <circle cx="87" cy="100" r="2" fill="#FFFFFF" opacity="0.8" />
      <circle cx="143" cy="100" r="2" fill="#FFFFFF" opacity="0.8" />
      </g>
      <g className="e-happy">
      <path d="M80 100 Q92 78 104 100 M136 100 Q148 78 160 100" fill="none" stroke="#6CF0FF" strokeWidth="7" strokeLinecap="round" filter={`url(#${uid}Blur)`} opacity="0.7" />
      <path d="M80 100 Q92 78 104 100 M136 100 Q148 78 160 100" fill="none" stroke="#9FF7FF" strokeWidth="6.5" strokeLinecap="round" />
      </g>
      <g className="e-star">
      <path d="M92 79 Q94.6 89.4 105 92 Q94.6 94.6 92 105 Q89.4 94.6 79 92 Q89.4 89.4 92 79 Z M148 79 Q150.6 89.4 161 92 Q150.6 94.6 148 105 Q145.4 94.6 135 92 Q145.4 89.4 148 79 Z" fill="#6CF0FF" filter={`url(#${uid}Blur)`} opacity="0.8" />
      <path d="M92 79 Q94.6 89.4 105 92 Q94.6 94.6 92 105 Q89.4 94.6 79 92 Q89.4 89.4 92 79 Z M148 79 Q150.6 89.4 161 92 Q150.6 94.6 148 105 Q145.4 94.6 135 92 Q145.4 89.4 148 79 Z" fill="#B8FBFF" />
      </g>
      <g className="e-flat">
      <rect x="80" y="90" width="24" height="7" rx="3.5" fill="#6CF0FF" opacity="0.5" />
      <rect x="136" y="90" width="24" height="7" rx="3.5" fill="#6CF0FF" opacity="0.5" />
      </g>
      </g>
      </g>
      <ellipse cx="72" cy="120" rx="9" ry="5" fill="#FF8FC0" opacity="0.4" />
      <ellipse cx="168" cy="120" rx="9" ry="5" fill="#FF8FC0" opacity="0.4" />
      <path className="m-smile" d="M104 118 Q120 130 136 118" fill="none" stroke="#9FF7FF" strokeWidth="5" strokeLinecap="round" />
      <g className="m-open">
      <path d="M102 115 Q120 140 138 115 Q120 122 102 115 Z" fill="#9FF7FF" />
      <path d="M112 127 Q120 133 128 127 Q120 124 112 127 Z" fill="#FF8FC0" opacity="0.85" />
      </g>
      <ellipse className="m-o" cx="120" cy="122" rx="6" ry="6" fill="none" stroke="#9FF7FF" strokeWidth="4" />
      <path className="m-wavy" d="M106 122 Q113 117 120 122 Q127 127 134 122" fill="none" stroke="#9FF7FF" strokeWidth="4" strokeLinecap="round" />
      <path className="m-flat" d="M108 122 H132" fill="none" stroke="#9FF7FF" strokeWidth="4" strokeLinecap="round" opacity="0.55" />
      </g>
      </g>
      </g>
      <g className="fx fx-think">
      <circle className="orb orb1" cx="120" cy="40" r="5" fill="#6CF0FF" />
      <circle className="orb orb2" cx="120" cy="40" r="4" fill="#9FF7FF" />
      <circle className="orb orb3" cx="120" cy="40" r="3.5" fill="#3FA9FF" />
      </g>
      <g className="fx fx-burst">
      <path className="bst bst1" d="M30 39 Q31.4 44.6 37 46 Q31.4 47.4 30 53 Q28.6 47.4 23 46 Q28.6 44.6 30 39 Z" fill="#9FF7FF" />
      <path className="bst bst2" d="M210 31 Q211.8 38.2 219 40 Q211.8 41.8 210 49 Q208.2 41.8 201 40 Q208.2 38.2 210 31 Z" fill="#6CF0FF" />
      <path className="bst bst3" d="M218 122 Q219.2 126.8 224 128 Q219.2 129.2 218 134 Q216.8 129.2 212 128 Q216.8 126.8 218 122 Z" fill="#FFD27A" />
      <path className="bst bst4" d="M22 130 Q23.2 134.8 28 136 Q23.2 137.2 22 142 Q20.8 137.2 16 136 Q20.8 134.8 22 130 Z" fill="#FF8FC0" />
      </g>
      <g className="fx fx-ring"><circle className="wave" cx="120" cy="120" r="72" fill="none" stroke="#6CF0FF" strokeWidth="3" /></g>
      <g className="fx fx-check">
      <g className="pop">
      <circle cx="208" cy="32" r="16" fill="#6CF0FF" fillOpacity="0.22" stroke="#6CF0FF" strokeWidth="2.2" />
      <path d="M200 32 L205.5 37.5 L216 26.5" fill="none" stroke="#B8FBFF" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
      </g>
      </g>
      <g className="fx fx-support">
      <path className="chev chev1" d="M26 118 L16 128 L26 138" fill="none" stroke="#6CF0FF" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      <path className="chev chev2" d="M40 118 L30 128 L40 138" fill="none" stroke="#6CF0FF" strokeWidth="4" strokeLinecap="round" strokeLinejoin="round" />
      </g>
      <g className="fx fx-unsure">
      <g className="bob">
      <circle cx="208" cy="32" r="16" fill="#F5A524" fillOpacity="0.2" stroke="#FFB84D" strokeWidth="2.2" />
      <path d="M203 27 Q203 21 208 21 Q213 21 213 26 Q213 30 208 32 V35" fill="none" stroke="#FFC566" strokeWidth="2.8" strokeLinecap="round" />
      <circle cx="208" cy="40.5" r="1.9" fill="#FFC566" />
      </g>
      </g>
      <g className="fx fx-error">
      <circle cx="208" cy="32" r="16" fill="#F5A524" fillOpacity="0.2" stroke="#FFB84D" strokeWidth="2.2" />
      <path d="M208 24 V34" fill="none" stroke="#FFC566" strokeWidth="3" strokeLinecap="round" />
      <circle cx="208" cy="40" r="1.9" fill="#FFC566" />
      </g>
      </g>
    </svg>
  );
});
