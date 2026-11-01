/** Decorative inline illustrations for empty and welcome states. Inline SVG (not img/data URLs) keeps the strict
 *  `img-src 'self' blob:` CSP intact; colours come from Shell.css theme tokens through the `art-*` classes. */
export function Illustration({ kind, className }: { kind: 'conversation' | 'people'; className?: string }) {
  return <svg className={`illustration${className ? ` ${className}` : ''}`} viewBox="0 0 200 160" aria-hidden="true" focusable="false">
    <circle className="art-bg" cx="100" cy="84" r="66" />
    {kind === 'conversation' ? <>
      <path className="art-card" d="M50 36h68a18 18 0 0 1 18 18v14a18 18 0 0 1-18 18H62l-16 12V86.5A18 18 0 0 1 32 68V54a18 18 0 0 1 18-18z" />
      <rect className="art-line" x="50" y="52" width="58" height="7" rx="3.5" />
      <rect className="art-line-soft" x="50" y="65" width="38" height="7" rx="3.5" />
      <path className="art-brand" d="M86 92h66a18 18 0 0 1 18 18v6a18 18 0 0 1-4.5 11.9V140l-13-6.4A18 18 0 0 1 152 134H86a18 18 0 0 1-18-18v-6a18 18 0 0 1 18-18z" />
      <circle className="art-on-brand" cx="102" cy="113" r="4.5" />
      <circle className="art-on-brand" cx="118" cy="113" r="4.5" />
      <circle className="art-on-brand" cx="134" cy="113" r="4.5" />
      <path className="art-spark" d="M160 40v12M154 46h12M40 112v8M36 116h8" />
    </> : <>
      <rect className="art-card" x="44" y="38" width="112" height="88" rx="20" />
      <circle className="art-brand-soft" cx="80" cy="72" r="15" />
      <path className="art-brand-soft" d="M58 110a22 22 0 0 1 44 0z" />
      <rect className="art-line" x="110" y="64" width="34" height="8" rx="4" />
      <rect className="art-line-soft" x="110" y="80" width="24" height="8" rx="4" />
      <circle className="art-brand" cx="154" cy="42" r="17" />
      <path className="art-on-brand-stroke" d="M154 35v14M147 42h14" />
      <path className="art-spark" d="M36 54v10M31 59h10" />
    </>}
  </svg>;
}
