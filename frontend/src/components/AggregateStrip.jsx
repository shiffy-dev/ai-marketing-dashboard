import useSWR from 'swr'
import { aggregateKey } from '../api.js'

function Chips({ title, entries }) {
  return (
    <div className="card p-6 shadow-card">
      <p className="mb-4 text-eyebrow uppercase text-soft">{title}</p>
      {entries.length ? (
        <ul className="flex flex-wrap gap-2">
          {entries.slice(0, 8).map((e) => (
            <li
              key={e.label}
              className="inline-flex items-center gap-2 rounded-full border border-rule bg-page-soft px-3 py-1 text-sm text-ink"
            >
              <span className="capitalize">{e.label}</span>
              <span className="rounded-full bg-brand px-2 text-xs font-bold text-white">{e.count}</span>
            </li>
          ))}
        </ul>
      ) : (
        <p className="text-sm text-soft">Appears once analyses finish.</p>
      )}
    </div>
  )
}

export default function AggregateStrip({ platform, relevant }) {
  const { data } = useSWR(aggregateKey(platform, relevant), { refreshInterval: (d) => (d && d.analyzed < d.total ? 8000 : 0) })
  if (!data || !data.total) return null
  return (
    <div className="mb-10">
      <div className="mb-4 flex flex-wrap items-baseline justify-between gap-2">
        <h3 className="text-h3">What the top {data.total} have in common</h3>
        <p className="text-xs text-soft">
          {data.analyzed} of {data.total} analyzed
        </p>
      </div>
      <div className="grid gap-4 md:grid-cols-2">
        <Chips title="Most-used hook techniques" entries={data.hook_techniques} />
        <Chips title="Recurring formats" entries={data.format_tags} />
      </div>
    </div>
  )
}
