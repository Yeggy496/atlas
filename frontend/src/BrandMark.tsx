/** An open day arc, a clock hand, and one reserved time slot. */
export function BrandMark({ className = "" }: { className?: string }) {
  return (
    <svg className={`brand-symbol ${className}`} viewBox="0 0 48 48" fill="none" aria-hidden="true">
      <rect width="48" height="48" rx="13" fill="#365d4c" />
      <path d="M35.5 22A12 12 0 1 1 26 12.2" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" />
      <path d="M24 17v8l6 3" stroke="#fff" strokeWidth="3.2" strokeLinecap="round" strokeLinejoin="round" />
      <rect x="31" y="10" width="8" height="8" rx="2.2" fill="#d8b76b" />
    </svg>
  );
}
