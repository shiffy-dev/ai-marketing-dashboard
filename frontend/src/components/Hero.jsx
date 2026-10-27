import {
  formatCompact,
  formatDateTime,
  formatPercent,
  formatRatio,
  formatVelocity,
  median,
  timeAgo,
} from "../format.js";
import { Badge, Eyebrow, Skeleton } from "./ui.jsx";

function Stat({ value, label, hint }) {
  return (
    <div className="card min-w-0 p-4 shadow-card sm:p-6">
      <p className="text-[11px] font-semibold uppercase tracking-wider text-soft">
        {label}
      </p>
      <p className="mt-2 text-[clamp(24px,3vw,36px)] font-extrabold leading-none tracking-tight tabular-nums text-navy">
        {value}
      </p>
      {hint && <p className="mt-1 text-xs text-soft">{hint}</p>}
    </div>
  );
}

export default function Hero({
  platform,
  data,
  isLoading,
  relevant,
  onRelevant,
  onRefresh,
  refreshing,
}) {
  const items = data?.items || [];
  const metrics = items.map((i) => i.metrics || {});
  const youtube = platform === "youtube";
  const dataset = data?.dataset;

  return (
    <section className="bg-page-soft">
      <div className="mx-auto grid max-w-page gap-12 px-5 py-16 md:px-gutter md:py-section lg:grid-cols-[1.2fr_1fr] lg:items-center">
        <div>
          <Eyebrow>
            {youtube
              ? "Trending now in UAE· YouTube Shorts"
              : "Tracked UAE accounts · Instagram Reels"}
          </Eyebrow>
          <h1 className="max-w-[16em] text-h1">
            {youtube
              ? "What’s winning on UAE Shorts — and why."
              : "What’s winning on UAE Reels — and why."}
          </h1>
          <p className="mt-6 max-w-lede text-lede text-muted">
            {youtube
              ? "The ten fastest-moving 30–60 second Shorts on YouTube’s official UAE trending charts, ranked by views per hour and how far they outrun their channel size — with an evidence-backed breakdown of why each one works."
              : dataset?.sample
                ? "Sample data. These are placeholder reels so the Instagram view is never empty — drop a real export at data/instagram_reels.json to replace them."
                : `Top reels from tracked UAE accounts, scraped via Apify. Data as of ${dataset?.scraped_at ? formatDateTime(dataset.scraped_at) : "—"} GST.`}
          </p>
          <div className="mt-8 flex flex-col gap-3 sm:flex-row sm:flex-wrap sm:items-center">
            <button
              className="btn btn-primary"
              onClick={onRefresh}
              disabled={refreshing}
            >
              {refreshing
                ? youtube
                  ? "Refreshing…"
                  : "Scraping via Apify (1–3 min)…"
                : youtube
                  ? "Refresh from YouTube"
                  : "Refresh from Instagram"}
            </button>
            {youtube && (
              <>
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
                Last updated {formatDateTime(data.last_updated)} GST (
                {timeAgo(data.last_updated)})
              </span>
            )}
            {data?.cached && (
              <Badge tone="amber" title={data.error || "Refresh failed"}>
                Cached data · refresh failed
              </Badge>
            )}
            {youtube && relevant && <span>· Music &amp; gaming excluded</span>}
            {!youtube && dataset?.sample && (
              <Badge tone="amber" title={`Loaded from ${dataset.file}`}>
                Sample data
              </Badge>
            )}
            {!youtube && dataset && !dataset.sample && (
              <Badge
                tone="green"
                title={`${dataset.reel_count} reels from ${dataset.source}`}
              >
                {dataset.source === "apify" ? "Apify scrape" : "Dataset"}
              </Badge>
            )}
          </div>
        </div>

        <div>
          <p className="mb-4 border-b-2 border-navy pb-3 text-eyebrow uppercase text-soft">
            This week’s top {items.length || 10}
          </p>
          <div className="grid grid-cols-2 gap-3 sm:gap-4">
            {isLoading && !data ? (
              Array.from({ length: 4 }, (_, i) => (
                <div key={i}>
                  <Skeleton className="h-24 w-full rounded-card" />
                </div>
              ))
            ) : (
              <>
                <Stat
                  value={formatVelocity(median(metrics.map((m) => m.velocity)))}
                  label="Median velocity"
                  hint={
                    youtube
                      ? "Views per hour since publish"
                      : "Plays per hour since publish"
                  }
                />
                <Stat
                  value={formatRatio(
                    Math.max(0, ...metrics.map((m) => m.outlier_ratio ?? 0)) ||
                      null,
                  )}
                  label="Top outlier"
                  hint={youtube ? "Views ÷ subscribers" : "Plays ÷ followers"}
                />
                <Stat
                  value={formatPercent(
                    median(metrics.map((m) => m.engagement_rate)),
                  )}
                  label="Median engagement"
                  hint="(Likes + comments) ÷ views"
                />
                <Stat
                  value={formatCompact(
                    items.reduce((sum, i) => sum + (i.views || 0), 0) || null,
                  )}
                  label={youtube ? "Total views" : "Total plays"}
                  hint={`Across the top ${items.length || 10}`}
                />
              </>
            )}
          </div>
        </div>
      </div>
    </section>
  );
}
