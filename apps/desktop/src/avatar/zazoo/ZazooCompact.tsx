/**
 * Compact static Zazoo icon — no director, no animation loop.
 * Renders Zazoo's head in a fixed square, suitable for icon slots,
 * chat panel headers, and avatar hover overlays.
 */
export function ZazooCompact({ size = 32, className }: { size?: number; className?: string }) {
  const s = size;
  return (
    <svg
      width={s}
      height={s}
      viewBox="0 0 64 64"
      role="img"
      aria-label="Zazoo"
      className={className}
      style={{ display: "block" }}
    >
      {/* Felt body glow */}
      <radialGradient id="zc-body" cx="42%" cy="30%" r="70%">
        <stop offset="0%" stopColor="#FAF0DF" />
        <stop offset="100%" stopColor="#E8D4B0" />
      </radialGradient>

      {/* Left ear */}
      <ellipse cx="18" cy="14" rx="7" ry="10" fill="url(#zc-body)" stroke="#2E4057" strokeWidth="1.4"
        transform="rotate(-18 18 14)" />
      <ellipse cx="18" cy="14" rx="3.5" ry="5.5" fill="#F5C6B8" opacity="0.7"
        transform="rotate(-18 18 14)" />

      {/* Right ear */}
      <ellipse cx="46" cy="14" rx="7" ry="10" fill="url(#zc-body)" stroke="#2E4057" strokeWidth="1.4"
        transform="rotate(18 46 14)" />
      <ellipse cx="46" cy="14" rx="3.5" ry="5.5" fill="#F5C6B8" opacity="0.7"
        transform="rotate(18 46 14)" />

      {/* Head */}
      <circle cx="32" cy="34" r="22" fill="url(#zc-body)" stroke="#2E4057" strokeWidth="1.4" />

      {/* Suit collar peeking in */}
      <path d="M18 52 Q24 58 32 58 Q40 58 46 52 L44 56 Q36 64 28 64 L20 56 Z"
        fill="#3E5A7E" opacity="0.85" />
      <path d="M26 56 L32 62 L38 56" fill="white" opacity="0.9" />

      {/* Left eye white */}
      <ellipse cx="23" cy="33" rx="7.5" ry="9" fill="white" stroke="#2E4057" strokeWidth="1" />
      {/* Left pupil */}
      <ellipse cx="23" cy="34" rx="4.5" ry="5.5" fill="#1A2B3C" />
      {/* Left eye sparkle */}
      <circle cx="25.5" cy="31.5" r="2" fill="white" opacity="0.9" />
      <circle cx="20.5" cy="36" r="1" fill="white" opacity="0.5" />

      {/* Right eye white */}
      <ellipse cx="41" cy="33" rx="7.5" ry="9" fill="white" stroke="#2E4057" strokeWidth="1" />
      {/* Right pupil */}
      <ellipse cx="41" cy="34" rx="4.5" ry="5.5" fill="#1A2B3C" />
      {/* Right eye sparkle */}
      <circle cx="43.5" cy="31.5" r="2" fill="white" opacity="0.9" />
      <circle cx="38.5" cy="36" r="1" fill="white" opacity="0.5" />

      {/* Nose — micro dot */}
      <circle cx="32" cy="43" r="1.5" fill="#2E4057" opacity="0.6" />

      {/* Mouth — thread line */}
      <path d="M28.5 45 Q32 49 35.5 45" fill="none" stroke="#2E4057" strokeWidth="1.2"
        strokeLinecap="round" opacity="0.7" />

      {/* Whiskers left */}
      <line x1="12" y1="42" x2="26" y2="44" stroke="#2E4057" strokeWidth="0.9" opacity="0.35" />
      <line x1="12" y1="45" x2="26" y2="46" stroke="#2E4057" strokeWidth="0.9" opacity="0.3" />

      {/* Whiskers right */}
      <line x1="52" y1="42" x2="38" y2="44" stroke="#2E4057" strokeWidth="0.9" opacity="0.35" />
      <line x1="52" y1="45" x2="38" y2="46" stroke="#2E4057" strokeWidth="0.9" opacity="0.3" />
    </svg>
  );
}
