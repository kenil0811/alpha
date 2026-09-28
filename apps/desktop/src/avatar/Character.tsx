/**
 * Alpha's placeholder character: a soft rounded shape with eyes that blink, a mouth that
 * changes with what Alpha is doing, and a gentle bob while idle. Kenil's own art replaces
 * this later; the moods stay the same so the window does not change.
 */
export type Mood = "idle" | "listening" | "thinking" | "talking" | "sorry";

export function Character({ mood, size = 96 }: { mood: Mood; size?: number }) {
  return (
    <svg className={`character character--${mood}`} width={size} height={size} viewBox="0 0 96 96" role="img" aria-label={`Alpha is ${mood === "idle" ? "here" : mood}`}>
      <defs>
        <radialGradient id="character-body" cx="40%" cy="35%" r="70%">
          <stop offset="0%" stopColor="var(--avatar-hi, #8fb4ff)" />
          <stop offset="100%" stopColor="var(--avatar-lo, #3d63d6)" />
        </radialGradient>
      </defs>
      <g className="character__body">
        <path d="M48 8c22 0 38 16 38 38 0 14-7 26-19 33l3 9-13-5c-3 .6-6 1-9 1C26 84 10 68 10 46S26 8 48 8z" fill="url(#character-body)" />
        <g className="character__eyes">
          <ellipse className="character__eye" cx="36" cy="44" rx="4.5" ry="6" fill="#0d1020" />
          <ellipse className="character__eye" cx="60" cy="44" rx="4.5" ry="6" fill="#0d1020" />
          <circle cx="37.5" cy="41.5" r="1.6" fill="#fff" />
          <circle cx="61.5" cy="41.5" r="1.6" fill="#fff" />
        </g>
        {mood === "thinking" ? (
          <g className="character__dots" fill="#0d1020">
            <circle cx="40" cy="62" r="2.2" />
            <circle cx="48" cy="62" r="2.2" />
            <circle cx="56" cy="62" r="2.2" />
          </g>
        ) : mood === "talking" ? (
          <ellipse className="character__mouth" cx="48" cy="62" rx="7" ry="4.5" fill="#0d1020" />
        ) : mood === "sorry" ? (
          <path d="M40 66q8-6 16 0" stroke="#0d1020" strokeWidth="2.5" fill="none" strokeLinecap="round" />
        ) : mood === "listening" ? (
          <circle cx="48" cy="62" r="3.5" fill="#0d1020" />
        ) : (
          <path d="M39 60q9 8 18 0" stroke="#0d1020" strokeWidth="2.5" fill="none" strokeLinecap="round" />
        )}
      </g>
    </svg>
  );
}
