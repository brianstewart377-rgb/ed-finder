// ─── Logo — minimal "compass / star reticle" mark ─────────────────────────
export function Logo() {
  return (
    <div
      className="relative w-10 h-10 rounded-chunk-sm grid place-items-center"
      style={{
        background: 'radial-gradient(circle at 30% 25%, rgba(111,229,255,0.15), transparent 38%), linear-gradient(135deg, #1c1f24 0%, #0a0c10 100%)',
        boxShadow:
          'inset 0 1px 0 rgba(255,255,255,0.08), 0 0 0 1px rgba(255,122,20,0.4), 0 0 12px -2px rgba(255,122,20,0.5), 0 10px 22px -18px rgba(111,229,255,0.55)',
      }}
    >
      <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="#ff7a14" strokeWidth="1.6" strokeLinecap="round">
        <circle cx="12" cy="12" r="9" stroke="#ff7a14" strokeOpacity="0.85" />
        <path d="M12 3v18M3 12h18" stroke="#c8ccd1" strokeOpacity="0.5" />
        <path d="M12 7l2.5 5L12 17l-2.5-5L12 7z" fill="#ff7a14" stroke="#ff7a14" />
      </svg>
    </div>
  );
}
