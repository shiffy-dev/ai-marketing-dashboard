import useSWR from 'swr'
import { analysisKey } from '../api.js'
import { formatCompact, formatRatio, formatVelocity, timeAgo } from '../format.js'
import { Badge, ConfidenceBadge, Skeleton } from './ui.jsx'

export function useAnalysis(platform, videoId) {
  return useSWR(videoId ? analysisKey(platform, videoId) : null)
}

export default function VideoCard({ item, onOpen }) {
  const { data, error, isLoading } = useAnalysis(item.platform, item.video_id)
  const analysis = data?.analysis
  const m = item.metrics || {}
  const plays = item.platform === 'youtube' ? 'views' : 'plays'

  return (
    <article className="card group overflow-hidden hover:shadow-lift">
      <button onClick={() => onOpen(item)} className="flex h-full flex-col text-left" aria-label={`Open analysis for ${item.title}`}>
        <div className="relative aspect-video w-full overflow-hidden bg-rule-soft">
          {item.thumbnail && (
            <img
              src={item.thumbnail}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.02]"
            />
          )}
          <span className="absolute left-3 top-3 rounded-md bg-navy px-2.5 py-1 text-sm font-bold text-white">
            #{item.rank}
          </span>
        </div>
        <div className="flex flex-1 flex-col gap-3 p-6">
          <div className="flex flex-wrap gap-2">
            <Badge tone="brand" title="Views per hour since publish">
              {formatVelocity(m.velocity)}
            </Badge>
            <Badge tone="cyan" title={item.followers_or_subs ? `${formatCompact(item.views)} ${plays} ÷ ${formatCompact(item.followers_or_subs)} audience` : 'Audience size hidden'}>
              {m.outlier_ratio != null ? `${formatRatio(m.outlier_ratio)} outlier` : 'Audience hidden'}
            </Badge>
            {item.format === 'short' && <Badge title="Under 3 minutes">Short</Badge>}
            {isLoading && <Skeleton className="h-6 w-28 rounded-full" />}
            {analysis && <ConfidenceBadge level={analysis.confidence} />}
          </div>
          <h3 dir="auto" className="line-clamp-2 text-lede font-semibold text-ink">
            {item.title}
          </h3>
          <p dir="auto" className="text-sm text-muted">
            {item.channel}
            <span className="text-soft">
              {' '}· {formatCompact(item.views)} {plays} · {timeAgo(item.published_at)}
            </span>
          </p>
          <div className="mt-auto border-t border-rule pt-4">
            {isLoading && (
              <div className="space-y-2" aria-label="Analysing">
                <Skeleton className="h-3 w-24" />
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-4/5" />
              </div>
            )}
            {error && <p className="text-sm text-red">Analysis unavailable: {error.message}</p>}
            {data?.status === 'pending' && (
              <p className="text-sm text-soft" title="Run scripts/prewarm.py, or open this card and choose Analyze now">
                Analysis pending
              </p>
            )}
            {analysis && (
              <>
                <p className="mb-1 text-eyebrow uppercase text-brand">Why it&rsquo;s performing</p>
                <p className="line-clamp-3 text-sm text-body">{analysis.why_trending?.summary}</p>
                <p className="mt-3 text-sm font-bold text-brand group-hover:underline">Read the full breakdown →</p>
              </>
            )}
          </div>
        </div>
      </button>
    </article>
  )
}

export function VideoCardSkeleton() {
  return (
    <div className="card overflow-hidden">
      <Skeleton className="aspect-video w-full rounded-none" />
      <div className="space-y-3 p-6">
        <div className="flex gap-2">
          <Skeleton className="h-6 w-20 rounded-full" />
          <Skeleton className="h-6 w-24 rounded-full" />
        </div>
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-5 w-2/3" />
        <Skeleton className="h-3 w-1/2" />
      </div>
    </div>
  )
}
