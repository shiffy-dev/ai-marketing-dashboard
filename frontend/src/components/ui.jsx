export function Eyebrow({ children, className = '' }) {
  return (
    <p className={`mb-5 flex items-center gap-3 text-eyebrow uppercase text-brand ${className}`}>
      <span aria-hidden className="h-hairline w-rule rounded-full bg-cyan" />
      {children}
    </p>
  )
}

export function Section({ eyebrow, title, children, action, soft = false, id }) {
  return (
    <section id={id} className={soft ? 'bg-page-soft' : 'bg-page'}>
      <div className="mx-auto max-w-page px-5 py-16 md:px-gutter md:py-section">
        {eyebrow && <Eyebrow>{eyebrow}</Eyebrow>}
        {(title || action) && (
          <div className="mb-8 flex flex-col gap-4 border-b-2 border-navy pb-6 md:flex-row md:items-end md:justify-between">
            {title && <h2 className="text-h2">{title}</h2>}
            {action}
          </div>
        )}
        {children}
      </div>
    </section>
  )
}

const BADGE_TONES = {
  brand: 'bg-brand-tint text-brand',
  cyan: 'bg-cyan-tint text-brand',
  green: 'bg-green-tint text-green',
  amber: 'bg-amber-tint text-amber',
  red: 'bg-red-tint text-red',
  neutral: 'bg-rule-soft text-muted',
}

export function Badge({ tone = 'neutral', children, title }) {
  return (
    <span
      title={title}
      className={`inline-flex items-center gap-1 whitespace-nowrap rounded-full px-2.5 py-0.5 text-xs font-semibold ${BADGE_TONES[tone]}`}
    >
      {children}
    </span>
  )
}

const CONFIDENCE_TONE = { high: 'green', medium: 'amber', low: 'red' }

export function ConfidenceBadge({ level, label = 'confidence' }) {
  if (!level) return null
  return (
    <Badge tone={CONFIDENCE_TONE[level] || 'neutral'} title={`${level} ${label}`}>
      <span aria-hidden className="h-1.5 w-1.5 rounded-full bg-current" />
      {level[0].toUpperCase() + level.slice(1)} {label}
    </Badge>
  )
}

export function Skeleton({ className = '' }) {
  return <div aria-hidden className={`skeleton ${className}`} />
}

export function Notice({ tone = 'neutral', title, children, action }) {
  const tones = {
    neutral: 'border-rule bg-page-soft',
    error: 'border-red-tint bg-red-tint',
    warning: 'border-amber-tint bg-amber-tint',
  }
  return (
    <div role={tone === 'error' ? 'alert' : 'status'} className={`rounded-card border p-6 ${tones[tone]}`}>
      {title && <p className="mb-1 font-semibold text-ink">{title}</p>}
      {children && <div className="text-card text-muted">{children}</div>}
      {action && <div className="mt-4">{action}</div>}
    </div>
  )
}
