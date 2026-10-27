const PLATFORMS = [
  { id: 'youtube', label: 'YouTube' },
  { id: 'instagram', label: 'Instagram Reels' },
]

export default function Header({ platform, onPlatform }) {
  return (
    <header className="sticky top-0 z-30 border-b border-rule bg-white">
      <div className="mx-auto flex max-w-page flex-wrap items-center justify-between gap-4 px-5 py-4 md:px-gutter">
        <div className="flex items-center gap-4">
          <span className="text-lede font-bold tracking-tight text-navy">
            Trend<span className="text-brand">Brief</span>
          </span>
          <span aria-hidden className="hidden h-6 w-px bg-rule sm:block" />
          <span
            className="inline-flex items-center gap-2 rounded-full border border-cyan-soft bg-cyan-tint px-3 py-1 text-xs font-semibold text-brand"
            title="Market: United Arab Emirates (AE)"
          >
            <span aria-hidden className="h-2 w-2 rounded-full bg-cyan" />
            UAE market
          </span>
        </div>
        <div role="tablist" aria-label="Platform" className="inline-flex rounded-md border border-rule bg-page-soft p-1">
          {PLATFORMS.map((p) => {
            const active = p.id === platform
            return (
              <button
                key={p.id}
                role="tab"
                aria-selected={active}
                onClick={() => onPlatform(p.id)}
                className={`rounded-md px-4 py-2 text-sm font-semibold transition-colors ${
                  active ? 'bg-brand text-white shadow-button' : 'text-muted hover:text-brand'
                }`}
              >
                {p.label}
              </button>
            )
          })}
        </div>
      </div>
    </header>
  )
}
