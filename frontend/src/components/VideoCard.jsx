import useSWR from "swr";
import { analysisKey } from "../api.js";
import {
  formatCompact,
  formatDuration,
  formatPercent,
  formatRatio,
  timeAgo,
} from "../format.js";
import { Skeleton } from "./ui.jsx";

export function useAnalysis(platform, videoId) {
  return useSWR(videoId ? analysisKey(platform, videoId) : null);
}

const CONFIDENCE_DOT = { high: "bg-green", medium: "bg-amber", low: "bg-red" };

function Metric({ label, value, title }) {
  return (
    <div title={title} className="min-w-0">
      <dt className="text-[11px] font-semibold uppercase tracking-wider text-soft">
        {label}
      </dt>
      <dd className="mt-0.5 truncate text-base font-bold tabular-nums text-navy sm:text-lede">
        {value}
      </dd>
    </div>
  );
}

export default function VideoCard({ item, onOpen }) {
  const { data, error, isLoading } = useAnalysis(item.platform, item.video_id);
  const analysis = data?.analysis;
  const m = item.metrics || {};
  const plays = item.platform === "youtube" ? "views" : "plays";

  return (
    <article className="card group overflow-hidden shadow-card transition duration-200 hover:-translate-y-0.5 hover:border-cyan hover:shadow-lift">
      <button
        onClick={() => onOpen(item)}
        className="grid h-full w-full grid-cols-[96px_1fr] text-left sm:grid-cols-[144px_1fr]"
        aria-label={`Open analysis for ${item.title}`}
      >
        <div className="relative aspect-[9/16] self-start overflow-hidden bg-navy">
          {item.thumbnail && (
            <img
              src={item.thumbnail}
              alt=""
              loading="lazy"
              className="h-full w-full object-cover transition-transform duration-300 group-hover:scale-[1.03]"
            />
          )}
          <span className="absolute left-2 top-2 rounded-md bg-white/95 px-2 py-0.5 text-base font-extrabold tabular-nums text-brand shadow-card">
            {String(item.rank).padStart(2, "0")}
          </span>
          {item.duration_seconds != null && (
            <span className="absolute bottom-2 right-2 rounded-sm bg-navy/80 px-1.5 py-0.5 text-[11px] font-semibold tabular-nums text-white">
              {formatDuration(item.duration_seconds)}
            </span>
          )}
        </div>

        <div className="flex min-w-0 flex-col p-4 sm:p-5">
          <p dir="auto" className="truncate text-xs font-semibold text-soft">
            {item.channel} · {timeAgo(item.published_at)}
          </p>
          <h3
            dir="auto"
            className="mt-1 line-clamp-2 text-card font-semibold text-ink"
          >
            {item.title}
          </h3>

          <dl className="mt-3 grid grid-cols-3 gap-2 border-y sm:gap-3 border-rule py-3">
            <Metric
              label={`${plays}/hr`}
              value={formatCompact(m.velocity)}
              title="Velocity: views per hour since publish"
            />
            <Metric
              label="Outlier"
              value={formatRatio(m.outlier_ratio)}
              title={
                item.followers_or_subs
                  ? `${formatCompact(item.views)} ${plays} ÷ ${formatCompact(item.followers_or_subs)} audience`
                  : "Audience size hidden"
              }
            />
            <Metric
              label="Engage"
              value={formatPercent(m.engagement_rate)}
              title="(Likes + comments) ÷ views"
            />
          </dl>

          <div className="mt-3 flex-1">
            {isLoading && (
              <div className="space-y-2" aria-label="Analysing">
                <Skeleton className="h-3 w-full" />
                <Skeleton className="h-3 w-4/5" />
              </div>
            )}
            {error && (
              <p className="text-sm text-red">
                Analysis unavailable: {error.message}
              </p>
            )}
            {data?.status === "pending" && (
              <p className="text-sm text-soft">
                Analysis not run yet — open to analyze.
              </p>
            )}
            {analysis && (
              <p className="line-clamp-4 text-sm text-body">
                <span className="font-semibold text-navy">Why it works: </span>
                {analysis.why_trending?.summary}
              </p>
            )}
          </div>

          <div className="mt-3 flex items-center justify-between text-xs">
            <span className="text-soft">
              {analysis?.confidence ? (
                <span className="inline-flex items-center gap-1.5 capitalize">
                  <span
                    aria-hidden
                    className={`h-1.5 w-1.5 rounded-full ${CONFIDENCE_DOT[analysis.confidence] || "bg-soft"}`}
                  />
                  {analysis.confidence} confidence
                </span>
              ) : (
                `${formatCompact(item.views)} ${plays}`
              )}
            </span>
            <span className="font-bold text-brand group-hover:underline">
              Breakdown →
            </span>
          </div>
        </div>
      </button>
    </article>
  );
}

export function VideoCardSkeleton() {
  return (
    <div className="card grid grid-cols-[96px_1fr] overflow-hidden sm:grid-cols-[144px_1fr]">
      <Skeleton className="aspect-[9/16] w-full rounded-none" />
      <div className="space-y-3 p-5">
        <Skeleton className="h-3 w-1/2" />
        <Skeleton className="h-5 w-full" />
        <Skeleton className="h-12 w-full" />
        <Skeleton className="h-3 w-4/5" />
      </div>
    </div>
  );
}
