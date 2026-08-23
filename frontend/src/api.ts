export type AvatarPhase = 'idle' | 'listening' | 'thinking' | 'speaking'

export interface AvatarState {
  phase: AvatarPhase
  emotion: string
  [key: string]: unknown
}

export type WsEvent =
  | { type: 'avatar_state'; state: AvatarState }
  | { type: 'speaking'; text: string }
  | { type: 'speaking_done'; text: string }
  | { type: 'tts_progress'; done: number; total: number }
  | { type: 'audio'; audio: string; text?: string; transcript?: string; sample_rate?: number; format?: string }
  | { type: 'error'; message: string; detail?: string }
  | { type: 'stopped' }
  | { type: 'pong' }

function blobToBase64(blob: Blob): Promise<string> {
  return new Promise((resolve, reject) => {
    const reader = new FileReader()
    reader.onloadend = () => {
      const dataUrl = reader.result as string
      const idx = dataUrl.indexOf(',')
      resolve(idx >= 0 ? dataUrl.slice(idx + 1) : dataUrl)
    }
    reader.onerror = () => reject(reader.error)
    reader.readAsDataURL(blob)
  })
}

export class WsClient {
  private ws: WebSocket | null = null
  private shouldReconnect = true
  private reconnectAttempt = 0
  private reconnectTimer: ReturnType<typeof setTimeout> | null = null
  private url: string
  private sessionId: string
  private onEvent: (ev: WsEvent) => void
  private onOpen?: () => void

  constructor(
    sessionId: string,
    onEvent: (ev: WsEvent) => void,
    onOpen?: () => void,
  ) {
    this.sessionId = sessionId
    this.onEvent = onEvent
    this.onOpen = onOpen
    const proto = location.protocol === 'https:' ? 'wss:' : 'ws:'
    this.url = `${proto}//${location.host}/ws/chat/${encodeURIComponent(sessionId)}/`
  }

  connect() {
    if (this.ws && (this.ws.readyState === WebSocket.OPEN || this.ws.readyState === WebSocket.CONNECTING)) return
    this.shouldReconnect = true
    // Defer socket creation by a microtask so a StrictMode teardown (which
    // runs synchronously after mount in dev) can set shouldReconnect = false
    // before the socket is ever opened. That avoids opening a socket that is
    // immediately closed while still connecting.
    queueMicrotask(() => {
      if (!this.shouldReconnect) return
      this.openSocket()
    })
  }

  private openSocket() {
    this.ws = new WebSocket(this.url)
    this.ws.onopen = () => {
      this.reconnectAttempt = 0
      this.onOpen?.()
    }
    this.ws.onmessage = (e) => {
      try {
        const data = JSON.parse(e.data) as WsEvent
        this.onEvent(data)
      } catch {
        // ignore
      }
    }
    this.ws.onclose = () => {
      this.ws = null
      if (this.shouldReconnect) this.scheduleReconnect()
    }
    this.ws.onerror = () => {
      try { this.ws?.close() } catch {}
    }
  }

  private scheduleReconnect() {
    if (this.reconnectTimer) return
    const delay = Math.min(1000 * Math.pow(1.6, this.reconnectAttempt), 8000)
    this.reconnectAttempt += 1
    this.reconnectTimer = setTimeout(() => {
      this.reconnectTimer = null
      this.connect()
    }, delay)
  }

  private sendJson(obj: unknown) {
    if (!this.ws || this.ws.readyState !== WebSocket.OPEN) return false
    this.ws.send(JSON.stringify(obj))
    return true
  }

  async sendAudio(blob: Blob, sampleRate?: number) {
    const b64 = await blobToBase64(blob)
    this.sendJson({ type: 'audio', audio: b64, sample_rate: sampleRate ?? 48000, session_id: this.sessionId })
  }

  sendStop() {
    return this.sendJson({ type: 'stop', session_id: this.sessionId })
  }

  disconnect() {
    this.shouldReconnect = false
    if (this.reconnectTimer) {
      clearTimeout(this.reconnectTimer)
      this.reconnectTimer = null
    }
    try { this.ws?.close() } catch {}
    this.ws = null
  }

  get ready() {
    return this.ws?.readyState === WebSocket.OPEN
  }
}
