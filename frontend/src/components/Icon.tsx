/** Small hand-rolled line-icon set (stroke-based, currentColor) for the
 * sidebar/topbar shell — kept as one file rather than a dependency since
 * the app only needs ~20 fixed glyphs. */

export type IconName =
  | "overview"
  | "activity"
  | "news"
  | "social"
  | "briefcase"
  | "file-text"
  | "calendar"
  | "rotate"
  | "shield"
  | "target"
  | "star"
  | "bell"
  | "trending-up"
  | "calculator"
  | "search"
  | "sun"
  | "moon"
  | "user"
  | "chevron-down"
  | "arrow-up"
  | "arrow-down"
  | "minus"
  | "dot"
  | "refresh";

const PATHS: Record<IconName, React.ReactNode> = {
  overview: (
    <>
      <rect x="3" y="3" width="7" height="9" rx="1.5" />
      <rect x="14" y="3" width="7" height="5" rx="1.5" />
      <rect x="14" y="12" width="7" height="9" rx="1.5" />
      <rect x="3" y="16" width="7" height="5" rx="1.5" />
    </>
  ),
  activity: <polyline points="3 12 8 12 10 6 14 18 16 12 21 12" />,
  news: (
    <>
      <rect x="3" y="4" width="15" height="16" rx="1.5" />
      <path d="M18 8h3v10a2 2 0 0 1-2 2h-1" />
      <line x1="6.5" y1="8" x2="14.5" y2="8" />
      <line x1="6.5" y1="12" x2="14.5" y2="12" />
      <line x1="6.5" y1="16" x2="11" y2="16" />
    </>
  ),
  social: (
    <>
      <circle cx="9" cy="8" r="3.2" />
      <path d="M3.5 20a5.5 5.5 0 0 1 11 0" />
      <circle cx="17.5" cy="7" r="2.4" />
      <path d="M15 20a4.3 4.3 0 0 1 7 0" />
    </>
  ),
  briefcase: (
    <>
      <rect x="3" y="7.5" width="18" height="12" rx="1.5" />
      <path d="M8 7.5V6a2 2 0 0 1 2-2h4a2 2 0 0 1 2 2v1.5" />
      <line x1="3" y1="12.5" x2="21" y2="12.5" />
    </>
  ),
  "file-text": (
    <>
      <path d="M6 3h8l5 5v13a1 1 0 0 1-1 1H6a1 1 0 0 1-1-1V4a1 1 0 0 1 1-1z" />
      <polyline points="14 3 14 8 19 8" />
      <line x1="8" y1="13" x2="16" y2="13" />
      <line x1="8" y1="17" x2="13" y2="17" />
    </>
  ),
  calendar: (
    <>
      <rect x="3" y="5" width="18" height="16" rx="1.5" />
      <line x1="3" y1="10" x2="21" y2="10" />
      <line x1="8" y1="3" x2="8" y2="7" />
      <line x1="16" y1="3" x2="16" y2="7" />
    </>
  ),
  rotate: (
    <>
      <path d="M3 11a9 9 0 0 1 15.5-6.2L21 7" />
      <polyline points="21 3 21 7 17 7" />
      <path d="M21 13a9 9 0 0 1-15.5 6.2L3 17" />
      <polyline points="3 21 3 17 7 17" />
    </>
  ),
  shield: <path d="M12 2 4 5.5v6C4 16.5 7.4 20.7 12 22c4.6-1.3 8-5.5 8-10.5v-6L12 2z" />,
  target: (
    <>
      <circle cx="12" cy="12" r="8.5" />
      <circle cx="12" cy="12" r="4.8" />
      <circle cx="12" cy="12" r="1.1" />
    </>
  ),
  star: <path d="M12 2.5l2.9 6.2 6.6.8-4.9 4.6 1.3 6.6L12 17.6l-5.9 3.1 1.3-6.6-4.9-4.6 6.6-.8L12 2.5z" />,
  bell: (
    <>
      <path d="M6 9a6 6 0 0 1 12 0c0 5 2 6 2 6H4s2-1 2-6z" />
      <path d="M10 20a2 2 0 0 0 4 0" />
    </>
  ),
  "trending-up": (
    <>
      <polyline points="3 16 10 9 14 13 21 5" />
      <polyline points="15 5 21 5 21 11" />
    </>
  ),
  calculator: (
    <>
      <rect x="4" y="2.5" width="16" height="19" rx="1.5" />
      <line x1="8" y1="6.5" x2="16" y2="6.5" />
      <line x1="7.5" y1="11" x2="7.5" y2="11.02" />
      <line x1="12" y1="11" x2="12" y2="11.02" />
      <line x1="16.5" y1="11" x2="16.5" y2="11.02" />
      <line x1="7.5" y1="15" x2="7.5" y2="15.02" />
      <line x1="12" y1="15" x2="12" y2="15.02" />
      <line x1="16.5" y1="15" x2="16.5" y2="18.5" />
      <line x1="7.5" y1="18.5" x2="12" y2="18.5" />
    </>
  ),
  search: (
    <>
      <circle cx="10.5" cy="10.5" r="6.5" />
      <line x1="20" y1="20" x2="15.3" y2="15.3" />
    </>
  ),
  sun: (
    <>
      <circle cx="12" cy="12" r="4.2" />
      <line x1="12" y1="2" x2="12" y2="4.5" />
      <line x1="12" y1="19.5" x2="12" y2="22" />
      <line x1="4.2" y1="4.2" x2="6" y2="6" />
      <line x1="18" y1="18" x2="19.8" y2="19.8" />
      <line x1="2" y1="12" x2="4.5" y2="12" />
      <line x1="19.5" y1="12" x2="22" y2="12" />
      <line x1="4.2" y1="19.8" x2="6" y2="18" />
      <line x1="18" y1="6" x2="19.8" y2="4.2" />
    </>
  ),
  moon: <path d="M20 14.5A8.5 8.5 0 1 1 9.5 4a7 7 0 0 0 10.5 10.5z" />,
  user: (
    <>
      <circle cx="12" cy="8" r="4" />
      <path d="M4 20a8 8 0 0 1 16 0" />
    </>
  ),
  "chevron-down": <polyline points="6 9 12 15 18 9" />,
  "arrow-up": <polyline points="6 15 12 9 18 15" />,
  "arrow-down": <polyline points="6 9 12 15 18 9" />,
  minus: <line x1="5" y1="12" x2="19" y2="12" />,
  dot: <circle cx="12" cy="12" r="5" />,
  refresh: (
    <>
      <polyline points="21 2 21 8 15 8" />
      <path d="M20.5 13a8.5 8.5 0 1 1-2.3-7.5L21 8" />
    </>
  ),
};

export default function Icon({
  name,
  size = 18,
  className,
  strokeWidth = 1.8,
}: {
  name: IconName;
  size?: number;
  className?: string;
  strokeWidth?: number;
}) {
  const filled = name === "star" || name === "shield" || name === "dot" || name === "moon";
  return (
    <svg
      width={size}
      height={size}
      viewBox="0 0 24 24"
      fill={filled ? "currentColor" : "none"}
      stroke="currentColor"
      strokeWidth={strokeWidth}
      strokeLinecap="round"
      strokeLinejoin="round"
      className={className}
      aria-hidden="true"
    >
      {PATHS[name]}
    </svg>
  );
}
