/** WebSocket 杩炴帴锛氳嚜鍔ㄩ噸杩? + 浜嬩欢鍒嗗彂銆? */

type Handler = (event: Record<string, unknown>) => void

const listeners = new Set<Handler>()
let socket: WebSocket | null = null
let retryTimer: number | null = null
let retryDelay = 500
let stopped = false

function url(): string {
  const scheme = location.protocol === 'https:' ? 'wss' : 'ws'
  return `${scheme}://${location.host}/ws`
}

function connect(): void {
  if (stopped) return
  try {
    socket = new WebSocket(url())
  } catch {
    schedule()
    return
  }

  socket.onopen = () => {
    retryDelay = 500
  }

  socket.onmessage = (message) => {
    let payload: Record<string, unknown>
    try {
      payload = JSON.parse(message.data as string)
    } catch {
      return
    }
    for (const handler of listeners) {
      try {
        handler(payload)
      } catch (err) {
        console.error('[ws] handler error', err)
      }
    }
  }

  socket.onclose = () => {
    socket = null
    schedule()
  }

  socket.onerror = () => {
    socket?.close()
  }
}

function schedule(): void {
  if (stopped || retryTimer !== null) return
  retryTimer = window.setTimeout(() => {
    retryTimer = null
    retryDelay = Math.min(retryDelay * 1.7, 8000)
    connect()
  }, retryDelay)
}

export const bus = {
  start(): void {
    stopped = false
    if (!socket) connect()
  },
  stop(): void {
    stopped = true
    socket?.close()
  },
  on(handler: Handler): () => void {
    listeners.add(handler)
    return () => listeners.delete(handler)
  },
}
