import { formatCompact, formatDateTime, formatPercent, formatRatio, formatVelocity, median, timeAgo } from '../format.js'
import { Badge, Eyebrow, Skeleton } from './ui.jsx'

function Stat({ value, label, hint }) {
  return (
    <div className="min-w-0">
      <p className="font-serif text-stat text-brand">{value}</p>
      <p className="mt-2 text-eyebrow uppercase text-ink">{label}</p>
      {hint && <p className="mt-1 text-xs text-soft">{hint}</p>}
    </div>
  )
}

export default function Hero({ platform, data, isLoading, relevant, onRelevant, onRefresh, refreshing }) {
  const items = data?.items || []
  const metrics = items.map((i) => i.metrics || {})
  const youtube = platform === 'youtube'

  return (
    <section className="bg-page-soft">
      <div className="mx-auto grid max-w-page gap-12 px-5 py-16 md:px-gutter md:py-section lg:grid-cols-[1.25fr_1fr] lg:items-end">
        <div>
          <Eyebrow>{youtube ? 'UAE trending now · YouTube' : 'Tracked UAE accounts · Instagram Reels'}</Eyebrow>
          <h1 className="max-w-[16em] text-h1">Why the UAE&rsquo;s top videos are winning right now.</h1>
          <p className="mt-6 max-w-lede text-lede text-muted">
            {youtube
              ? 'The ten fastest-moving videos on YouTube in the UAE, ranked by views per hour and how far they outperform their channel size, with an evidence-backed breakdown of hook, body, CTA and why each one is working.'
              : 'Trending among tracked UAE accounts, from a curated dataset. Not a platform-wide ranking.'}
          </p>
          <div className="mt-8 flex flex-wrap items-center gap-3">
            {youtube && (
              <>
                <button className="btn btn-primary" onClick={onRefresh} disabled={refreshing}>
                  {refreshing ? 'Refreshing…' : 'Refresh from YouTube'}
                </button>
                <label className="btn btn-secondary cursor-pointer select-none">
                  <input
                    type="checkbox"
                    className="h-4 w-4 accent-brand"
                    checked={relevant}
                    onChange={(e) => onRelevant(e.target.checked)}
                  />
                  Marketing-relevant only
                </label>
              </>
            )}
          </div>
          <div className="mt-6 flex flex-wrap items-center gap-2 text-xs text-soft">
            {data?.last_updated && (
              <span title={formatDateTime(data.last_updated)}>
                Last updated {formatDateTime(data.last_updated)} GST ({timeAgo(data.last_updated)})
              </span>
            )}
            {data?.cached && (
              <Badge tone="amber" title={data.error || 'Refresh failed'}>
                Cached data · refresh failed
              </Badge>
            )}
            {youtube && relevant && <span>· Music &amp; gaming excluded</span>}
          </div>
        </div>

        <div className="grid grid-cols-2 gap-x-8 gap-y-10 border-t-2 border-navy pt-8">
          {isLoading && !data ? (
            Array.from({ length: 4 }, (_, i) => (
              <div key={i}>
                <Skeleton className="h-12 w-28" />
                <Skeleton className="mt-3 h-3 w-24" />
              </div>
            ))
          ) : (
            <>
              <Stat
                value={formatVelocity(median(metrics.map((m) => m.velocity)))}
                label="Median velocity"
                hint={youtube ? 'Views per hour since publish' : 'Plays per hour since publish'}
              />
              <Stat
                value={formatRatio(Math.max(0, ...metrics.map((m) => m.outlier_ratio ?? 0)) || null)}
                label="Top outlier"
                hint={youtube ? 'Views ÷ subscribers' : 'Plays ÷ followers'}
              />
              <Stat
                value={formatPercent(median(metrics.map((m) => m.engagement_rate)))}
                label="Median engagement"
                hint="(Likes + comments) ÷ views"
              />
              <Stat
                value={formatCompact(items.reduce((sum, i) => sum + (i.views || 0), 0) || null)}
                label={youtube ? 'Total views' : 'Total plays'}
                hint={`Across the top ${items.length || 10}`}
              />
            </>
          )}
        </div>
      </div>
    </section>
  )
}
