const compact = new Intl.NumberFormat('en', { notation: 'compact', maximumFractionDigits: 1 })

export const formatCompact = (n) => (n == null ? '—' : compact.format(n))

export const formatPercent = (r, digits = 1) => (r == null ? '—' : `${(r * 100).toFixed(digits)}%`)

export const formatRatio = (r) => {
  if (r == null) return '—'
  if (r >= 10) return `${Math.round(r)}×`
  if (r >= 1) return `${r.toFixed(1)}×`
  return `${r.toFixed(2)}×`
}

export const formatDuration = (s) => (s == null ? '—' : `${Math.floor(s / 60)}:${String(s % 60).padStart(2, '0')}`)

export const formatVelocity = (v) => (v == null ? '—' : `${compact.format(v)}/h`)

export function formatDateTime(iso) {
  if (!iso) return '—'
  return new Date(iso).toLocaleString('en-AE', {
    dateStyle: 'medium',
    timeStyle: 'short',
    timeZone: 'Asia/Dubai',
  })
}

export function timeAgo(iso) {
  if (!iso) return ''
  const hours = (Date.now() - new Date(iso).getTime()) / 36e5
  if (hours < 1) return 'under an hour ago'
  if (hours < 48) return `${Math.round(hours)}h ago`
  return `${Math.round(hours / 24)}d ago`
}

export function median(values) {
  const v = values.filter((x) => x != null).sort((a, b) => a - b)
  if (!v.length) return null
  const mid = Math.floor(v.length / 2)
  return v.length % 2 ? v[mid] : (v[mid - 1] + v[mid]) / 2
}
