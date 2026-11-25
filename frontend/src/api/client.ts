/** 与后端通信的唯一入口。所有请求都走相对路径，桌面壳与浏览器预览一致。 */

export type JobStatus = 'queued' | 'running' | 'done' | 'failed' | 'cancelled'
export type JobKind = 'vod' | 'live'

export interface Variant {
  width: number
  height: number
  codecs: string
  fps: number
  bandwidth: number
  label: string
}

export interface ProbeResult {
  kind: JobKind | 'unknown'
  recognized: boolean
  reason: string
  variants: Variant[]
  looksLikePlaylist: boolean
}

export interface Job {
  id: string
  source: string
  title: string
  variant: string
  kind: JobKind
  status: JobStatus
  outDir: string
  fileHint: string
  bytesTotal: number
  logPath: string
  note: string
  createdAt: number
  updatedAt: number
}

export interface ProgressPayload {
  phase: 'fetching' | 'recording' | 'waiting'
  done: number
  total: number
  percent: number
  haveBytes: number
  totalBytes: number
  speed: string
  eta: string
}

export interface Settings {
  output_dir: string
  downloader_exe: string
  remuxer_exe: string
  parallel_fragments: number
  fragment_retries: number
  request_timeout: number
  speed_limit_kib: number
  keep_temp: boolean
  extra_headers: string
  proxy_mode: 'system' | 'manual' | 'none'
  manual_proxy: string
  referer: string
  live_realtime_merge: boolean
  live_keep_fragments: boolean
  live_stop_after: string
  live_poll_interval: number
  remux_after_done: string
  remux_imports: string
  decrypt_engine: 'ffmpeg' | 'mp4decrypt' | 'shaka'
  decrypt_tool_path: string
  decrypt_keys: string
  decrypt_key_file: string
  accent: string
  theme: 'auto' | 'light' | 'dark'
  locale: string
  clear_form_after_submit: boolean
  check_update_on_launch: boolean
}

export interface StartPayload {
  url: string
  title?: string
  outDir?: string
  variantWidth?: number
  variantHeight?: number
  variantFps?: number
  isLive?: boolean
  keepTemp?: boolean
}

export interface BatchItem {
  title: string
  url: string
}

async function request<T>(path: string, init?: RequestInit): Promise<T> {
  const response = await fetch(path, {
    headers: { 'Content-Type': 'application/json' },
    ...init,
  })
  if (!response.ok) {
    let detail = `HTTP ${response.status}`
    try {
      const body = await response.json()
      if (body?.detail) detail = typeof body.detail === 'string' ? body.detail : JSON.stringify(body.detail)
    } catch {
      /* 忽略解析失败 */
    }
    throw new Error(detail)
  }
  if (response.status === 204) return undefined as T
  return (await response.json()) as T
}

export const api = {
  health: () => request<{ ok: boolean; version: string; engine: string; engineReady: boolean }>('/api/health'),

  getSettings: () => request<Settings>('/api/settings'),
  patchSettings: (patch: Partial<Settings>) =>
    request<Settings>('/api/settings', { method: 'PATCH', body: JSON.stringify({ patch }) }),
  resetSettings: () => request<Settings>('/api/settings/reset', { method: 'POST' }),

  probe: (url: string) =>
    request<ProbeResult>('/api/probe', { method: 'POST', body: JSON.stringify({ url }) }),

  listJobs: (status: JobStatus | 'all' = 'all') =>
    request<{ jobs: Job[]; active: number }>(`/api/jobs?status=${encodeURIComponent(status)}`),
  startJob: (payload: StartPayload) =>
    request<Job>('/api/jobs', { method: 'POST', body: JSON.stringify(payload) }),
  startBatch: (items: BatchItem[], outDir = '') =>
    request<{ created: Job[]; skipped: string[] }>('/api/jobs/batch', {
      method: 'POST',
      body: JSON.stringify({ items, outDir }),
    }),
  cancelJob: (id: string) => request<{ ok: boolean }>(`/api/jobs/${id}/cancel`, { method: 'POST' }),
  retryJob: (id: string) => request<Job>(`/api/jobs/${id}/retry`, { method: 'POST' }),
  deleteJob: (id: string, purge = false) =>
    request<{ ok: boolean; removedFile: boolean }>(`/api/jobs/${id}?purge=${purge}`, { method: 'DELETE' }),
  jobLog: (id: string, tail = 400) => request<{ lines: string[] }>(`/api/jobs/${id}/log?tail=${tail}`),

  pickDir: (path = '') =>
    request<{ path: string }>('/api/fs/pick-dir', { method: 'POST', body: JSON.stringify({ path }) }),
  reveal: (path: string) =>
    request<{ ok: boolean }>('/api/fs/reveal', { method: 'POST', body: JSON.stringify({ path }) }),

  thumbUrl: (name: string) => `/api/thumbs/${encodeURIComponent(name)}`,
}
