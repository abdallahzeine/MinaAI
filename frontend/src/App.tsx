import { useCallback, useEffect, useRef, useState } from 'react'
import type { CSSProperties } from 'react'
import { Loader2, Mic, MicOff, MicVocal, RotateCcw, Volume2, VolumeX } from 'lucide-react'
import FaceDemo from './FaceDemo'
import './App.css'
import { WsClient, type AvatarState, type WsEvent } from './api'

const IDLE: AvatarState = { phase: 'idle', emotion: 'neutral' }
export const SPEAKING: AvatarState = { phase: 'speaking', emotion: 'neutral' }

function getSessionId() {
  const key = 'mina_session_id'
  let v = localStorage.getItem(key)
  if (!v) {
    v = crypto.randomUUID()
    localStorage.setItem(key, v)
  }
  return v
}

function App() {
  const [avatar, setAvatar] = useState<AvatarState>(IDLE)
  const [isRecording, setIsRecording] = useState(false)
  const [transcript, setTranscript] = useState('')
  const [error, setError] = useState<string | null>(null)
  const [muted, setMuted] = useState(false)
  const [hasAudio, setHasAudio] = useState(false)
  const [isAudioLoading, setIsAudioLoading] = useState(false)
  const [isTtsPending, setIsTtsPending] = useState(false)
  const [ttsProgress, setTtsProgress] = useState<{ done: number; total: number } | null>(null)
  const [replayError, setReplayError] = useState(false)
  const mediaRecorderRef = useRef<MediaRecorder | null>(null)
  const chunksRef = useRef<Blob[]>([])
  const streamRef = useRef<MediaStream | null>(null)
  const wsRef = useRef<WsClient | null>(null)
  const sessionIdRef = useRef('')
  const accRef = useRef('')
  // Audio playback for Silma TTS (server-side, cuda:0, same GPU as 4B LLM)
  const audioRef = useRef<HTMLAudioElement | null>(null)
  const audioUrlRef = useRef<string | null>(null)
  const lastAudioB64Ref = useRef<string | null>(null)
  const mutedRef = useRef(muted)
  const generationRef = useRef(0)
  const isAudioLoadingRef = useRef(false)
  const hasAudioRef = useRef(false)

  useEffect(() => {
    mutedRef.current = muted
  }, [muted])

  useEffect(() => {
    isAudioLoadingRef.current = isAudioLoading
  }, [isAudioLoading])

  useEffect(() => {
    hasAudioRef.current = hasAudio
  }, [hasAudio])

  const cleanupAudio = useCallback(() => {
    const a = audioRef.current
    if (a) {
      try {
        a.pause()
        a.src = ''
        a.load()
      } catch {}
      // remove listeners to avoid leaks
      a.onplay = null
      a.onended = null
      a.onerror = null
      a.onpause = null
    }
    audioRef.current = null
    if (audioUrlRef.current) {
      try {
        URL.revokeObjectURL(audioUrlRef.current)
      } catch {}
      audioUrlRef.current = null
    }
  }, [])

  const invalidateAudioForNewRequest = useCallback(() => {
    generationRef.current += 1
    lastAudioB64Ref.current = null
    setHasAudio(false)
    setIsAudioLoading(true)
    setIsTtsPending(false)
    setTtsProgress(null)
    setReplayError(false)
    // Stop any ongoing playback immediately
    try {
      const a = audioRef.current
      if (a) a.pause()
    } catch {}
    cleanupAudio()
  }, [cleanupAudio])

  const playWav = useCallback((b64: string) => {
    // Store for replay regardless of muted state — versioned to current generation
    lastAudioB64Ref.current = b64
    setHasAudio(true)
    setIsAudioLoading(false)
    setReplayError(false)
    try {
      // Cleanup previous
      cleanupAudio()
      const binary = atob(b64)
      const len = binary.length
      const bytes = new Uint8Array(len)
      for (let i = 0; i < len; i++) bytes[i] = binary.charCodeAt(i)
      const blob = new Blob([bytes], { type: 'audio/wav' })
      const url = URL.createObjectURL(blob)
      audioUrlRef.current = url
      const audio = new Audio(url)
      audio.preload = 'auto'
      // Preserve lip-sync: avatar speaks while audio plays, idle when ends
      audio.onplay = () => setAvatar(SPEAKING)
      audio.onended = () => {
        setAvatar(IDLE)
        // keep url for replay until next audio or reset
      }
      audio.onerror = () => {
        setAvatar(IDLE)
        // Keep audio for retry but surface error styling
        setReplayError(true)
      }
      audio.onpause = () => {
        // If paused due to mute or reset, return to idle unless ended
        if (!audio.ended) setAvatar(IDLE)
      }
      audioRef.current = audio
      // Set speaking immediately for lip-sync (before play promise resolves)
      setAvatar(SPEAKING)
      void audio.play().catch((err) => {
        console.warn('[Audio] play() rejected (autoplay policy or interruption)', err)
        setAvatar(IDLE)
        // Autoplay block is not a synthesis error, but allow user to retry via Replay
        // Do not mark replayError so border stays normal; keep hasAudio true
      })
    } catch (e) {
      console.error('[Audio] failed to decode/play wav', e)
      setAvatar(IDLE)
      setReplayError(true)
      setIsAudioLoading(false)
      // keep hasAudio true if we have stored b64 for retry? But decode failed = corrupt
      // In that case clear it so replay doesn't loop on corrupt data
      lastAudioB64Ref.current = null
      setHasAudio(false)
    }
  }, [cleanupAudio])

  const playB64Audio = useCallback(
    (b64: string, textForAvatar?: string) => {
      // Store for replay regardless of muted state
      lastAudioB64Ref.current = b64
      setHasAudio(true)
      setIsAudioLoading(false)
      setIsTtsPending(false)
      setTtsProgress(null)
      setReplayError(false)
      if (textForAvatar) {
        accRef.current = textForAvatar
        setTranscript(textForAvatar)
      }
      if (mutedRef.current) {
        // Mute handling: simple pause — don't autoplay while muted
        // Keep avatar idle, await unmute + replay
        setAvatar(IDLE)
        return
      }
      playWav(b64)
    },
    [playWav],
  )

  const replayLast = useCallback(() => {
    // Guard against stale replay on new text: use generation-aware state flags
    if (isAudioLoadingRef.current || !hasAudioRef.current) return
    const stored = lastAudioB64Ref.current
    if (!stored) return
    playWav(stored)
  }, [playWav])

  useEffect(() => {
    sessionIdRef.current = getSessionId()
    const ws = new WsClient(sessionIdRef.current, (ev: WsEvent) => {
      switch (ev.type) {
        case 'avatar_state': {
          if (ev.state) {
            // Backend signals LLM-phase start via avatar_state('thinking'), not a separate
            // 'thinking' event. On thinking: clear stale transcript and invalidate old audio
            // so Replay cannot launch a stale wav for the new request.
            if (ev.state.phase === 'thinking') {
              setTranscript('')
              accRef.current = ''
              setError(null)
              invalidateAudioForNewRequest()
            }
            setAvatar(ev.state)
            // Failure path: backend sends idle when TTS synthesizes None (no audio will follow).
            // If we are still loading, clear loading so replay doesn't spin forever.
            if (ev.state.phase === 'idle' && isAudioLoadingRef.current) {
              // Don't clear if we are in the middle of speaking -> audio is expected.
              // Idle here means no audio payload will arrive.
              // Use a short check: if hasAudio is still false, we are awaiting first audio for this generation
              if (!hasAudioRef.current) {
                setIsAudioLoading(false)
                setIsTtsPending(false)
                setTtsProgress(null)
              }
            }
          }
          break
        }
        case 'speaking': {
          const chunk = ev.text ?? ''
          accRef.current += chunk
          setTranscript(accRef.current)
          break
        }
        case 'speaking_done': {
          const full = ev.text ?? accRef.current
          accRef.current = full
          setTranscript(full)
          // Do NOT synthesize on frontend — Silma audio will arrive as 'audio' event from backend (cuda:0).
          // If no audio follows (TTS failure fallback), backend already sent avatar_state idle so we stay idle.
          // Keep avatar as is; audio handler will set speaking when wav arrives.
          if (!full.trim()) {
            setAvatar(IDLE)
            setIsAudioLoading(false)
            setIsTtsPending(false)
            setTtsProgress(null)
            setHasAudio(false)
            break
          }
          // LLM finished; backend now synthesizes Silma in batches — show generation ring
          // (green shadow progress around the avatar). Progress arrives via tts_progress.
          setIsTtsPending(true)
          break
        }
        case 'tts_progress': {
          // Only relevant while awaiting the wav for the current generation
          if (!isAudioLoadingRef.current) break
          const total = Number(ev.total) || 0
          const done = total > 0 ? Math.min(Math.max(Number(ev.done) || 0, 0), total) : Math.max(Number(ev.done) || 0, 0)
          setTtsProgress({ done, total })
          break
        }
        case 'audio': {
          const b64 = ev.audio ?? ''
          const txt = ev.text ?? ev.transcript ?? accRef.current
          if (!b64) {
            // No audio payload — treat as transcript only
            if (txt) {
              accRef.current = txt
              setTranscript(txt)
            }
            setAvatar(IDLE)
            setIsAudioLoading(false)
            setIsTtsPending(false)
            setTtsProgress(null)
            setHasAudio(false)
            break
          }
          // New wav from Silma on cuda:0 (same GPU as LLM), 150M bilingual, ~24kHz.
          // Play via audio element, avatar speaking while playing, idle when ends (lip-sync preserved).
          playB64Audio(b64, txt)
          break
        }
        case 'error': {
          const msg = ev.message ?? 'error'
          const detail = ev.detail
          setError(detail ? `${msg}: ${detail}` : msg)
          try {
            const a = audioRef.current
            if (a) a.pause()
          } catch {}
          cleanupAudio()
          lastAudioB64Ref.current = null
          generationRef.current += 1
          setIsAudioLoading(false)
          setIsTtsPending(false)
          setTtsProgress(null)
          setHasAudio(false)
          setReplayError(true)
          setAvatar(IDLE)
          break
        }
        case 'pong': {
          break
        }
        default: {
          console.warn('[WS] unknown event', ev)
          break
        }
      }
    })
    wsRef.current = ws
    ws.connect()
    return () => {
      try {
        const a = audioRef.current
        if (a) a.pause()
      } catch {}
      cleanupAudio()
      ws.disconnect()
    }
  }, [cleanupAudio, playB64Audio, invalidateAudioForNewRequest])

  const handleReset = () => {
    const mr = mediaRecorderRef.current
    if (mr && mr.state !== 'inactive') {
      mr.ondataavailable = null
      mr.onstop = null
      try {
        mr.stop()
      } catch {}
    }
    streamRef.current?.getTracks().forEach((t) => t.stop())
    streamRef.current = null
    mediaRecorderRef.current = null
    chunksRef.current = []
    setIsRecording(false)
    setTranscript('')
    accRef.current = ''
    setError(null)
    try {
      const a = audioRef.current
      if (a) a.pause()
    } catch {}
    cleanupAudio()
    lastAudioB64Ref.current = null
    generationRef.current += 1
    setHasAudio(false)
    setIsAudioLoading(false)
    setIsTtsPending(false)
    setTtsProgress(null)
    setReplayError(false)
    setAvatar(IDLE)
  }

  const toggleMic = async () => {
    if (isRecording) {
      mediaRecorderRef.current?.stop()
      return
    }
    try {
      // Stop any ongoing TTS playback before listening
      try {
        const a = audioRef.current
        if (a && !a.paused) a.pause()
      } catch {}
      const stream = await navigator.mediaDevices.getUserMedia({ audio: true })
      streamRef.current = stream
      chunksRef.current = []
      const mr = new MediaRecorder(stream, { mimeType: MediaRecorder.isTypeSupported('audio/webm') ? 'audio/webm' : undefined })
      mediaRecorderRef.current = mr
      mr.ondataavailable = (e) => {
        if (e.data.size > 0) chunksRef.current.push(e.data)
      }
      mr.onstop = () => {
        const blob = new Blob(chunksRef.current, { type: mr.mimeType || 'audio/webm' })
        stream.getTracks().forEach((t) => t.stop())
        streamRef.current = null
        mediaRecorderRef.current = null
        chunksRef.current = []
        setIsRecording(false)
        if (blob.size === 0) {
          setAvatar(IDLE)
          setIsAudioLoading(false)
          return
        }
        setTranscript('')
        accRef.current = ''
        setError(null)
        setAvatar({ phase: 'thinking', emotion: 'neutral' })
        // Kill old audio + show spinner instantly. Server 'thinking' ack re-runs this
        // (idempotent). No spin-forever risk: terminal paths (error / idle / sendAudio
        // rejection / audio) all clear isAudioLoading.
        invalidateAudioForNewRequest()
        wsRef.current?.sendAudio(blob).catch((err) => {
          console.error('[WS] sendAudio failed', err)
          setError(String(err))
          setAvatar(IDLE)
          setIsAudioLoading(false)
          setHasAudio(false)
          setReplayError(true)
        })
      }
      mr.start()
      setIsRecording(true)
      setAvatar({ phase: 'listening', emotion: 'neutral' })
    } catch (err) {
      console.error('[Mic] getUserMedia failed', err)
      const msg = err instanceof Error ? err.message : String(err)
      setError(msg.includes('NotAllowed') ? 'Microphone permission denied' : msg)
      setIsRecording(false)
    }
  }

  const genPct =
    ttsProgress && ttsProgress.total > 0 && ttsProgress.done > 0
      ? Math.min(100, Math.max(0, Math.round((ttsProgress.done / ttsProgress.total) * 100)))
      : null

  return (
    <div className="app">
      <div className="stage-wrap">
        {isTtsPending && (
          <div
            aria-hidden
            className={`progress-ring ${genPct === null ? 'indeterminate' : ''}`}
            style={genPct === null ? undefined : ({ '--p': genPct } as CSSProperties)}
          />
        )}
        <div className={`avatar-stage phase-${avatar.phase} ${isTtsPending ? 'is-generating' : ''}`}>
          <FaceDemo phase={avatar.phase} />
        </div>
      </div>

      {(transcript || isAudioLoading) && (
        <div className="transcript-box">

          {transcript}
          <button
            type="button"
            onClick={replayLast}
            title={replayError ? 'Synthesis failed — try again' : isAudioLoading ? (genPct !== null ? `Generating voice… ${genPct}%` : 'Generating voice…') : 'Replay cloned voice'}
            disabled={!hasAudio || isAudioLoading}
            className={`replay-btn ${isAudioLoading ? 'is-loading' : ''} ${replayError ? 'is-error' : ''}`}
            aria-busy={isAudioLoading}
          >
            {isAudioLoading ? <Loader2 size={14} className="replay-icon replay-spinner" /> : <Volume2 size={14} className="replay-icon" />}
            {isAudioLoading ? (genPct !== null ? `${genPct}%` : 'Loading…') : 'Replay'}
          </button>
        </div>
      )}

      <div className="controls">
        <button
          type="button"
          className={`mic-btn ${isRecording ? 'is-recording' : ''} phase-${avatar.phase}`}
          onClick={() => void toggleMic()}
          aria-pressed={isRecording}
          aria-label={isRecording ? 'Stop recording' : 'Start recording'}
          title={isRecording ? 'Stop — will send to Gemma' : 'Start mic'}
        >
          {avatar.phase === 'speaking' ? <MicVocal size={22} strokeWidth={2} /> : isRecording ? <MicOff size={22} strokeWidth={2} /> : <Mic size={22} strokeWidth={2} />}
        </button>
        <button type="button" className="reset-btn" onClick={handleReset} aria-label="Reset" title="Reset">
          <RotateCcw size={20} strokeWidth={2} />
        </button>
        <button
          type="button"
          className="reset-btn"
          onClick={() => {
            const next = !muted
            setMuted(next)
            // Mute handling: simple pause on audio element per plan
            const a = audioRef.current
            if (a) {
              if (next) {
                try {
                  a.pause()
                } catch {}
                setAvatar(IDLE)
              } else {
                // On unmute, do not auto-resume — user can press Replay.
                // If they expect resume, they can press Replay; keeping pause semantics simple.
              }
            }
          }}
          aria-label={muted ? 'Unmute' : 'Mute'}
          title={muted ? 'Unmuted voice will be silent — click to enable' : 'Mute readout — pauses audio'}
        >
          {muted ? <VolumeX size={20} strokeWidth={2} /> : <Volume2 size={20} strokeWidth={2} />}
        </button>
      </div>
      {error && <div className="error-banner" role="alert">{error}</div>}
      <div style={{ fontSize: 12, opacity: 0.6 }}>
        {avatar.phase === 'listening'
          ? 'Listening — tap again to send'
          : isTtsPending
            ? genPct !== null
              ? `Generating voice… ${genPct}%`
              : 'Generating voice…'
            : avatar.phase === 'thinking'
              ? 'Thinking…'
              : avatar.phase === 'speaking'
                ? 'Speaking…'
                : 'Tap mic and speak'}
      </div>
    </div>
  )
}

export default App
