export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

async function request(url, options) {
  const res = await fetch(url, options)
  let body = null
  try {
    body = await res.json()
  } catch {
    body = null
  }
  if (!res.ok) {
    throw new ApiError(body?.detail || `Request failed (${res.status})`, res.status)
  }
  return body
}

export const fetcher = (url) => request(url)

export const trendingKey = (platform, relevant) => `/api/trending?platform=${platform}&relevant=${relevant}`
export const aggregateKey = (platform, relevant) => `/api/aggregate?platform=${platform}&relevant=${relevant}`
export const analysisKey = (platform, videoId) => `/api/analysis/${platform}/${encodeURIComponent(videoId)}`

export const refreshYoutube = (relevant) => request(`/api/refresh/youtube?relevant=${relevant}`, { method: 'POST' })
export const generateAnalysis = (platform, videoId) => request(analysisKey(platform, videoId), { method: 'POST' })
