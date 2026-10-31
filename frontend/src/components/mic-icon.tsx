/** Microphone glyph for the voice screening controls, slashed when off; decorative, inherits the text colour. */
export function MicIcon({ off = false }: { off?: boolean }) {
  return (
    <svg aria-hidden="true" focusable="false" viewBox="0 0 24 24" className="mission-mic-icon" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
      <rect x="9" y="2" width="6" height="12" rx="3" fill={off ? "none" : "currentColor"} stroke={off ? "currentColor" : "none"} />
      <path d="M5 11a7 7 0 0 0 14 0M12 18v4M8 22h8" />
      {off && <path d="M3 3l18 18" />}
    </svg>
  );
}
