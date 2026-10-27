const PLATFORMS = [
  { id: "youtube", label: "YouTube", sub: "Shorts · 30–60s" },
  { id: "instagram", label: "Instagram", sub: "Reels" },
];

export default function Header({ platform, onPlatform }) {
  return (
    <header className="sticky top-0 z-30 border-b border-rule bg-white/95 backdrop-blur">
      <div className="mx-auto flex max-w-page items-center justify-between gap-3 px-5 md:px-gutter">
        <a
          href="/"
          className="flex min-w-0 items-center gap-3 py-3 md:gap-4 md:py-4"
        >
          <img
            src="/ecomma.png"
            alt="ecomma"
            className="h-6 w-auto shrink-0 md:h-8"
          />
          <span
            aria-hidden
            className="hidden h-7 w-0.5 shrink-0 rounded-full bg-cyan sm:block"
          />
          <span className="hidden min-w-0 leading-tight sm:block">
            <span className="block truncate text-sm font-bold text-navy md:text-base">
              AI Marketing Dashboard
            </span>
            <span className="hidden text-xs text-soft sm:block">
              Trend intelligence · UAE market
            </span>
          </span>
        </a>
        <nav
          role="tablist"
          aria-label="Platform"
          className="flex shrink-0 items-stretch self-stretch"
        >
          {PLATFORMS.map((p) => {
            const active = p.id === platform;
            return (
              <button
                key={p.id}
                role="tab"
                aria-selected={active}
                onClick={() => onPlatform(p.id)}
                className={`relative flex flex-col items-center justify-center px-3 text-center transition-colors md:px-6 ${
                  active ? "text-brand" : "text-ink hover:text-brand"
                }`}
              >
                <span className="text-sm font-semibold md:text-[17px]">
                  {p.label}
                </span>
                <span className="hidden text-xs text-brand md:block">
                  {p.sub}
                </span>
                <span
                  aria-hidden
                  className={`absolute inset-x-3 bottom-0 h-[3px] rounded-t-full bg-cyan transition-opacity md:inset-x-5 ${
                    active ? "opacity-100" : "opacity-0"
                  }`}
                />
              </button>
            );
          })}
        </nav>
      </div>
    </header>
  );
}
