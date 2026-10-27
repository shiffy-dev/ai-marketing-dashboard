import { useEffect, useState } from 'react'
import { generateAnalysis } from '../api.js'
import { formatCompact, formatPercent, formatRatio, formatVelocity, timeAgo } from '../format.js'
import { Badge, ConfidenceBadge, Eyebrow, Notice, Skeleton } from './ui.jsx'
import { useAnalysis } from './VideoCard.jsx'

const DRIVER_LABEL = { content: 'Content', distribution: 'Distribution', context: 'Context' }

function PartCard({ label, title, children }) {
  return (
    <div className="card p-6">
      <p className="mb-3 text-eyebrow uppercase text-brand">{label}</p>
      {title && (
        <p dir="auto" className="mb-2 text-card font-semibold text-ink">
          {title}
        </p>
      )}
      <div className="text-sm text-muted">{children}</div>
    </div>
  )
}

function Metric({ label, value }) {
  return (
    <div>
      <p className="text-eyebrow uppercase text-soft">{label}</p>
      <p className="mt-1 font-serif text-h3 font-bold text-brand">{value}</p>
    </div>
  )
}

function DrawerSkeleton() {
  return (
    <div className="space-y-4" aria-label="Analysing video">
      <div className="grid gap-4 md:grid-cols-3">
        {[0, 1, 2].map((i) => (
          <Skeleton key={i} className="h-36 rounded-card" />
        ))}
      </div>
      <Skeleton className="h-6 w-56" />
      <Skeleton className="h-24 rounded-card" />
      <Skeleton className="h-24 rounded-card" />
      <p className="text-sm text-soft">Analysing transcript, comments and thumbnail…</p>
    </div>
  )
}

export default function AnalysisDrawer({ item, onClose }) {
  const { data, error, isLoading, mutate } = useAnalysis(item.platform, item.video_id)
  const [generating, setGenerating] = useState(false)
  const [genError, setGenError] = useState(null)
  const a = data?.analysis
  const pending = data?.status === 'pending'
  const m = item.metrics || {}
  const ev = item.evidence

  const analyzeNow = async () => {
    setGenerating(true)
    setGenError(null)
    try {
      await generateAnalysis(item.platform, item.video_id)
      await mutate()
    } catch (e) {
      setGenError(e.message)
    } finally {
      setGenerating(false)
    }
  }

  useEffect(() => {
    const onKey = (e) => e.key === 'Escape' && onClose()
    document.addEventListener('keydown', onKey)
    document.body.style.overflow = 'hidden'
    return () => {
      document.removeEventListener('keydown', onKey)
      document.body.style.overflow = ''
    }
  }, [onClose])

  return (
    <div className="fixed inset-0 z-50 flex justify-end" role="dialog" aria-modal="true" aria-labelledby="drawer-title">
      <div className="absolute inset-0 bg-navy/50" onClick={onClose} />
      <div className="relative flex h-full w-full max-w-[920px] flex-col overflow-y-auto bg-white shadow-drawer">
        <div className="sticky top-0 z-10 flex items-center justify-between border-b border-rule bg-white px-6 py-4 md:px-10">
          <p className="text-eyebrow uppercase text-brand">#{item.rank} in the UAE</p>
          <button onClick={onClose} className="btn btn-secondary min-h-0 px-3 py-1.5" aria-label="Close">
            Close ✕
          </button>
        </div>

        <div className="space-y-12 px-6 py-8 md:px-10 md:py-10">
          <div className="grid gap-6 md:grid-cols-[280px_1fr]">
            {item.thumbnail && <img src={item.thumbnail} alt="" className="w-full rounded-card border border-rule" />}
            <div>
              <h2 id="drawer-title" dir="auto" className="text-band">
                {item.title}
              </h2>
              <p dir="auto" className="mt-2 text-sm text-muted">
                {item.channel}
                {item.followers_or_subs ? ` · ${formatCompact(item.followers_or_subs)} subscribers` : ''} ·{' '}
                {timeAgo(item.published_at)}
              </p>
              <div className="mt-4 flex flex-wrap gap-2">
                {a && <ConfidenceBadge level={a.confidence} label="overall confidence" />}
                {a?.language && <Badge>Language: {a.language}</Badge>}
                {item.category && <Badge>{item.category}</Badge>}
                {ev && (
                  <Badge tone={ev.transcript_source === 'captions' ? 'green' : 'amber'}>
                    {ev.transcript_source === 'captions' ? `Transcript (${ev.transcript_language || '?'})` : 'No transcript'}
                  </Badge>
                )}
                {ev && <Badge>{ev.comments_status === 'ok' ? `${ev.comments} comments read` : `Comments ${ev.comments_status}`}</Badge>}
              </div>
              {item.url && (
                <a href={item.url} target="_blank" rel="noreferrer" className="mt-4 inline-block text-sm font-bold text-brand hover:underline">
                  Watch on {item.platform === 'youtube' ? 'YouTube' : 'Instagram'} →
                </a>
              )}
            </div>
          </div>

          <div className="grid grid-cols-2 gap-6 border-y border-rule py-6 md:grid-cols-4">
            <Metric label="Views" value={formatCompact(item.views)} />
            <Metric label="Velocity" value={formatVelocity(m.velocity)} />
            <Metric label="Outlier" value={formatRatio(m.outlier_ratio)} />
            <Metric label="Engagement" value={formatPercent(m.engagement_rate, 2)} />
          </div>

          {isLoading && <DrawerSkeleton />}
          {generating && <DrawerSkeleton />}
          {error && (
            <Notice
              tone="error"
              title="Analysis unavailable"
              action={
                <button className="btn btn-secondary" onClick={() => mutate()}>
                  Try again
                </button>
              }
            >
              {error.message}
            </Notice>
          )}
          {genError && (
            <Notice tone="error" title="Analysis failed">
              {genError}
            </Notice>
          )}
          {pending && !generating && (
            <Notice
              title="Analysis pending"
              action={
                <button className="btn btn-primary" onClick={analyzeNow}>
                  Analyze now
                </button>
              }
            >
              No stored analysis for this video yet. Analyzing on the local model can take a few
              minutes on CPU — or run scripts/prewarm.py to analyze the whole top 10 offline.
            </Notice>
          )}

          {a && (
            <>
              <section>
                <Eyebrow>Hook · Body · CTA</Eyebrow>
                <div className="grid gap-4 md:grid-cols-3">
                  <PartCard label="Hook" title={a.hook?.text ? `“${a.hook.text}”` : null}>
                    <p>
                      <span className="font-semibold text-ink">Technique: </span>
                      {a.hook?.technique}
                    </p>
                  </PartCard>
                  <PartCard label="Body" title={a.body?.structure}>
                    <ul className="list-disc space-y-1 pl-4">
                      {(a.body?.key_beats || []).map((b, i) => (
                        <li key={i} dir="auto">
                          {b}
                        </li>
                      ))}
                    </ul>
                  </PartCard>
                  <PartCard label="CTA" title={a.cta?.text ? `“${a.cta.text}”` : 'No explicit CTA'}>
                    <p>
                      <span className="font-semibold text-ink">Type: </span>
                      {a.cta?.type}
                    </p>
                  </PartCard>
                </div>
              </section>

              <section className="rounded-card bg-page-soft p-6 md:p-8">
                <Eyebrow>Why it&rsquo;s performing</Eyebrow>
                <p className="text-lede text-ink">{a.why_trending?.summary}</p>
                <ol className="mt-8 space-y-4">
                  {(a.why_trending?.drivers || []).map((d, i) => (
                    <li key={i} className="card p-6 shadow-card">
                      <div className="mb-3 flex flex-wrap items-center gap-2">
                        <span className="font-serif text-h3 font-bold text-brand">{i + 1}</span>
                        <Badge tone="brand">{DRIVER_LABEL[d.type] || d.type}</Badge>
                        <ConfidenceBadge level={d.confidence} />
                      </div>
                      <p className="text-card font-semibold text-ink">{d.claim}</p>
                      <p dir="auto" className="mt-3 border-l-2 border-cyan pl-4 text-sm text-muted">
                        <span className="font-semibold text-brand">Evidence: </span>
                        {d.evidence}
                      </p>
                    </li>
                  ))}
                </ol>
                <div className="mt-8 grid gap-4 md:grid-cols-2">
                  <div className="card p-6">
                    <p className="mb-3 text-eyebrow uppercase text-brand">Takeaways for ecommerce</p>
                    <ul className="space-y-2 text-sm text-body">
                      {(a.why_trending?.takeaways || []).map((t, i) => (
                        <li key={i} className="flex gap-2">
                          <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 bg-cyan" />
                          {t}
                        </li>
                      ))}
                    </ul>
                  </div>
                  <div className="card p-6">
                    <p className="mb-3 text-eyebrow uppercase text-soft">Unknowns</p>
                    <ul className="space-y-2 text-sm text-muted">
                      {(a.why_trending?.unknowns || []).map((u, i) => (
                        <li key={i} className="flex gap-2">
                          <span aria-hidden className="mt-2 h-1.5 w-1.5 shrink-0 bg-soft" />
                          {u}
                        </li>
                      ))}
                    </ul>
                  </div>
                </div>
              </section>

              {a.format_tags?.length > 0 && (
                <div className="flex flex-wrap gap-2">
                  {a.format_tags.map((t) => (
                    <Badge key={t}>{t}</Badge>
                  ))}
                </div>
              )}
              <p className="text-xs text-soft">
                {data.model} · prompt {data.prompt_version} · generated {timeAgo(data.created_at)}
              </p>
            </>
          )}
        </div>
      </div>
    </div>
  )
}
