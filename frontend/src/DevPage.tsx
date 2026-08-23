import { useCallback, useEffect, useRef, useState } from 'react'
import {
  AlertTriangle,
  ArrowLeft,
  Brain,
  CheckCircle2,
  Cpu,
  Eye,
  EyeOff,
  Info,
  Key,
  Loader2,
  Mic,
  Play,
  RefreshCw,
  Search,
  Send,
  Sliders,
  Sparkles,
  Terminal,
  Volume2,
  Wifi,
  XCircle,
} from 'lucide-react'
import './DevPage.css'

export interface DevSettings {
  provider: string
  base_url: string
  model: string
  api_key: string
  temperature: number
  chat_history_window: number
  thinking_level: string
  thinking_budget: number
  extra_params: string
  system_prompt: string
  tts_provider: string
  tts_base_url: string
  tts_model: string
  tts_voice: string
  tts_api_key: string
  tts_speed: number
  tts_extra_params: string
}

export interface VoiceOption {
  id: string
  desc: string
  category: string
}

interface DevSettingsResponse {
  settings: DevSettings
  voices?: VoiceOption[]
}

interface TestConnectionResult {
  status: 'ok' | 'error'
  latency_ms?: number
  model?: string
  reply?: string
  message?: string
  status_code?: number
}

interface TestTTSResult {
  status: 'ok' | 'error'
  audio_b64?: string
  sample_rate?: number
  latency_ms?: number
  message?: string
}

interface ReasoningMeta {
  mandatory?: boolean
  default_enabled?: boolean
  supported_efforts?: string[]
  default_effort?: string
}

interface ModelInfoResult {
  status: 'ok' | 'error'
  target_model?: string
  matched?: boolean
  supports_thinking?: boolean
  supported_parameters?: string[]
  default_parameters?: Record<string, number | string | boolean>
  reasoning_info?: ReasoningMeta
  context_length?: number | null
  input_modalities?: string[]
  output_modalities?: string[]
  accepts_audio?: boolean
  not_matched_message?: string | null
  message?: string
}

interface TTSModelInfoResult {
  status: 'ok' | 'error'
  target_model?: string
  matched?: boolean
  provider_name?: string
  format?: string
  sample_rate?: number
  default_voice?: string
  voices?: { id: string; name: string }[]
  supported_voices_count?: number
  message?: string
}

function DevPage() {
  const [settings, setSettings] = useState<DevSettings>({
    provider: 'openai_compatible',
    base_url: 'https://openrouter.ai/api/v1',
    model: '',
    api_key: '',
    temperature: 0.7,
    chat_history_window: 10,
    thinking_level: '',
    thinking_budget: -1,
    extra_params: '',
    system_prompt: '',
    tts_provider: 'audar',
    tts_base_url: 'https://openrouter.ai/api/v1',
    tts_model: 'audarai/Audar-TTS-V1-Flash',
    tts_voice: 'demo_female_1',
    tts_api_key: '',
    tts_speed: 1.0,
    tts_extra_params: '',
  })

  const [voices, setVoices] = useState<VoiceOption[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)
  const [showApiKey, setShowApiKey] = useState(false)
  const [showTtsApiKey, setShowTtsApiKey] = useState(false)
  const isLlamaCpp = settings.provider === 'llama_cpp'
  const isRemoteTTS = settings.tts_provider === 'openai' || settings.tts_provider === 'openai_compatible'
  const isAudar = settings.tts_provider === 'audar'

  // Auto-save state
  const [saveStatus, setSaveStatus] = useState<'idle' | 'saving' | 'saved' | 'error'>('idle')
  const initialLoadRef = useRef(false)
  const saveTimeoutRef = useRef<number | null>(null)

  // Test connection state
  const [testing, setTesting] = useState(false)
  const [testResult, setTestResult] = useState<TestConnectionResult | null>(null)

  // TTS Test state
  const [testingTTS, setTestingTTS] = useState(false)
  const [ttsTestResult, setTtsTestResult] = useState<TestTTSResult | null>(null)
  const [ttsTestPhrase, setTtsTestPhrase] = useState('مرحبا بكم، هذا اختبار لتوليد الصوت بالذكاء الاصطناعي.')
  const [remoteApiVoices, setRemoteApiVoices] = useState<{ id: string; name: string }[]>([])
  const [fetchingVoices, setFetchingVoices] = useState(false)
  const [voiceFetchMsg, setVoiceFetchMsg] = useState<string | null>(null)
  const [inspectingTTS, setInspectingTTS] = useState(false)
  const [ttsModelInfo, setTtsModelInfo] = useState<TTSModelInfoResult | null>(null)
  const [voiceSearch, setVoiceSearch] = useState('')

  // Model inspection state
  const [inspecting, setInspecting] = useState(false)
  const [modelInfo, setModelInfo] = useState<ModelInfoResult | null>(null)

  const fetchTTSModelInfo = useCallback(async (baseUrl: string, modelId: string, apiKey: string) => {
    if (!baseUrl.trim() || !modelId.trim()) {
      setTtsModelInfo(null)
      return
    }
    try {
      setInspectingTTS(true)
      const res = await fetch('/api/dev/tts-model-info/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: baseUrl,
          model: modelId,
          api_key: apiKey,
        }),
      })
      const data = (await res.json()) as TTSModelInfoResult
      setTtsModelInfo(data)
      if (data.voices && Array.isArray(data.voices) && data.voices.length > 0) {
        setRemoteApiVoices(data.voices)
        setVoiceFetchMsg(`Loaded ${data.voices.length} voices from API.`)
      }
    } catch {
      setTtsModelInfo(null)
    } finally {
      setInspectingTTS(false)
    }
  }, [])

  const fetchModelInfo = useCallback(async (baseUrl: string, modelId: string, apiKey: string) => {
    if (!baseUrl.trim() || !modelId.trim()) {
      setModelInfo(null)
      return
    }
    try {
      setInspecting(true)
      const res = await fetch('/api/dev/model-info/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: baseUrl,
          model: modelId,
          api_key: apiKey,
        }),
      })
      const data = (await res.json()) as ModelInfoResult
      setModelInfo(data)
    } catch {
      setModelInfo(null)
    } finally {
      setInspecting(false)
    }
  }, [])

  const loadSettings = useCallback(async () => {
    try {
      setLoading(true)
      const res = await fetch('/api/dev/settings/')
      if (!res.ok) throw new Error(`HTTP error ${res.status}`)
      const data = (await res.json()) as DevSettingsResponse
      setSettings(data.settings)
      if (data.voices) setVoices(data.voices)
      setError(null)
      initialLoadRef.current = true
      if (data.settings.base_url) {
        void fetchModelInfo(data.settings.base_url, data.settings.model, data.settings.api_key)
      }
      if (data.settings.tts_provider !== 'audar' && data.settings.tts_model) {
        const ttsUrl = data.settings.tts_base_url || 'https://openrouter.ai/api/v1'
        const ttsKey = data.settings.tts_api_key || data.settings.api_key
        void fetchTTSModelInfo(ttsUrl, data.settings.tts_model, ttsKey)
      }
    } catch (err) {
      setError(err instanceof Error ? err.message : String(err))
    } finally {
      setLoading(false)
    }
  }, [fetchModelInfo, fetchTTSModelInfo])

  useEffect(() => {
    void loadSettings()
  }, [loadSettings])

  // Debounced Auto-Save on Change
  useEffect(() => {
    if (!initialLoadRef.current) return

    if (saveTimeoutRef.current) {
      clearTimeout(saveTimeoutRef.current)
    }

    setSaveStatus('saving')
    saveTimeoutRef.current = window.setTimeout(async () => {
      try {
        const res = await fetch('/api/dev/settings/', {
          method: 'PUT',
          headers: { 'Content-Type': 'application/json' },
          body: JSON.stringify(settings),
        })
        if (!res.ok) {
          throw new Error(`Auto-save failed (HTTP ${res.status})`)
        }
        setSaveStatus('saved')
        setError(null)
      } catch (err) {
        setSaveStatus('error')
        setError(err instanceof Error ? err.message : String(err))
      }
    }, 600)

    return () => {
      if (saveTimeoutRef.current) {
        clearTimeout(saveTimeoutRef.current)
      }
    }
  }, [settings])

  const applyModelDefaultsDirectly = useCallback((data: ModelInfoResult) => {
    const defaults = data.default_parameters || {}
    const reasoning = data.reasoning_info || {}

    setSettings((prev) => {
      const next = { ...prev }

      // Set temperature if recommended, else standard 0.7
      if (typeof defaults.temperature === 'number') {
        next.temperature = defaults.temperature
      }

      // Set thinking level if recommended, else clear
      if (reasoning.default_effort) {
        next.thinking_level = reasoning.default_effort
      } else {
        next.thinking_level = ''
      }

      // Build extra params from API recommendations only
      const extraObj: Record<string, unknown> = {}
      Object.entries(defaults).forEach(([k, v]) => {
        if (k !== 'temperature') {
          extraObj[k] = v
        }
      })

      // If model has recommended extra params, set them; otherwise CLEAR them completely
      if (Object.keys(extraObj).length > 0) {
        next.extra_params = JSON.stringify(extraObj, null, 2)
      } else {
        next.extra_params = ''
      }

      return next
    })
  }, [])

  const handleInspectModel = async (overrideModel?: string) => {
    const targetModel = overrideModel !== undefined ? overrideModel : settings.model
    if (!settings.base_url.trim()) {
      setError('Please provide a Base URL to pull parameter information from the API.')
      return
    }
    try {
      setInspecting(true)
      setModelInfo(null)
      setError(null)
      const res = await fetch('/api/dev/model-info/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: settings.base_url,
          model: targetModel,
          api_key: settings.api_key,
        }),
      })
      const data = (await res.json()) as ModelInfoResult
      setModelInfo(data)

      // Automatically apply the model's recommended default parameters directly
      if (data.status === 'ok' && data.matched) {
        applyModelDefaultsDirectly(data)
      }

      if (data.status === 'error') {
        setError(data.message || 'Failed to pull parameter info from API.')
      }
    } catch (err) {
      setModelInfo({
        status: 'error',
        message: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setInspecting(false)
    }
  }

  const handleTestConnection = async () => {
    if (!settings.base_url.trim() || !settings.model.trim()) {
      setError('Please provide both Base URL and Model ID before testing.')
      return
    }
    try {
      setTesting(true)
      setTestResult(null)
      setError(null)
      const res = await fetch('/api/dev/test-connection/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: settings.base_url,
          model: settings.model,
          api_key: settings.api_key,
          extra_params: settings.extra_params,
          prompt: 'Hello! Reply in 5 words confirming you are ready.',
        }),
      })
      const data = (await res.json()) as TestConnectionResult
      setTestResult(data)
    } catch (err) {
      setTestResult({
        status: 'error',
        message: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setTesting(false)
    }
  }

  const handleInspectTTSModel = async (overrideModel?: string) => {
    const targetModel = overrideModel !== undefined ? overrideModel : settings.tts_model
    const targetBaseUrl = (settings.tts_base_url || settings.base_url || 'https://openrouter.ai/api/v1').trim()
    const targetApiKey = (settings.tts_api_key || settings.api_key || '').trim()
    if (!targetBaseUrl) {
      setError('Please provide a TTS Base URL to pull TTS info from the API.')
      return
    }
    try {
      setInspectingTTS(true)
      setTtsModelInfo(null)
      setError(null)
      const res = await fetch('/api/dev/tts-model-info/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: targetBaseUrl,
          model: targetModel,
          api_key: targetApiKey,
        }),
      })
      const data = (await res.json()) as TTSModelInfoResult
      setTtsModelInfo(data)
      if (data.voices && Array.isArray(data.voices) && data.voices.length > 0) {
        setRemoteApiVoices(data.voices)
        setVoiceFetchMsg(`Loaded ${data.voices.length} voices from API.`)
        if (data.default_voice && (!settings.tts_voice || !data.voices.some((v) => v.id === settings.tts_voice))) {
          setSettings((prev) => ({ ...prev, tts_voice: data.default_voice || prev.tts_voice }))
        }
      }
      if (data.status === 'error') {
        setError(data.message || 'Failed to pull TTS info from API.')
      }
    } catch (err) {
      setTtsModelInfo({
        status: 'error',
        message: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setInspectingTTS(false)
    }
  }

  const handleTestTTS = async () => {
    const targetBaseUrl = (settings.tts_base_url || settings.base_url || 'https://openrouter.ai/api/v1').trim()
    const targetApiKey = (settings.tts_api_key || settings.api_key || '').trim()
    try {
      setTestingTTS(true)
      setTtsTestResult(null)
      setError(null)
      const res = await fetch('/api/dev/test-tts/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          provider: settings.tts_provider,
          model: settings.tts_model,
          voice: settings.tts_voice,
          speed: settings.tts_speed,
          text: ttsTestPhrase,
          extra_params: settings.tts_extra_params,
          base_url: targetBaseUrl,
          api_key: targetApiKey,
        }),
      })
      const data = (await res.json()) as TestTTSResult
      setTtsTestResult(data)
    } catch (err) {
      setTtsTestResult({
        status: 'error',
        message: err instanceof Error ? err.message : String(err),
      })
    } finally {
      setTestingTTS(false)
    }
  }

  const handleFetchRemoteVoices = async () => {
    const targetBaseUrl = (settings.tts_base_url || settings.base_url || 'https://openrouter.ai/api/v1').trim()
    const targetApiKey = (settings.tts_api_key || settings.api_key || '').trim()
    if (!targetBaseUrl) {
      setError('Please provide a TTS Base URL to pull voices from the API.')
      return
    }
    try {
      setFetchingVoices(true)
      setVoiceFetchMsg(null)
      setError(null)
      const res = await fetch('/api/dev/tts-voices/', {
        method: 'POST',
        headers: { 'Content-Type': 'application/json' },
        body: JSON.stringify({
          base_url: targetBaseUrl,
          model: settings.tts_model,
          api_key: targetApiKey,
        }),
      })
      const data = await res.json()
      if (data.voices && Array.isArray(data.voices) && data.voices.length > 0) {
        setRemoteApiVoices(data.voices)
        setVoiceFetchMsg(`Loaded ${data.voices.length} voices from API.`)
        if (!settings.tts_voice || !data.voices.some((v: { id: string }) => v.id === settings.tts_voice)) {
          setSettings((prev) => ({ ...prev, tts_voice: data.voices[0].id }))
        }
      } else {
        setVoiceFetchMsg(data.message || 'Endpoint did not return a voice catalog. Enter voice name directly.')
      }
    } catch {
      setVoiceFetchMsg('Failed to query voices from endpoint API. Enter voice name directly.')
    } finally {
      setFetchingVoices(false)
    }
  }

  const supportedParams = modelInfo?.supported_parameters || []
  const hasSupportedParams = supportedParams.length > 0
  const apiEfforts = modelInfo?.reasoning_info?.supported_efforts || []
  const hasModelInfoContent = Boolean(
    modelInfo &&
      modelInfo.status === 'ok' &&
      settings.model.trim() &&
      (modelInfo.matched || modelInfo.not_matched_message)
  )

  if (loading) {
    return (
      <div className="dev-page">
        <div className="dev-loading-state">
          <Loader2 size={32} className="spin" />
          <p>Loading settings…</p>
        </div>
      </div>
    )
  }

  return (
    <div className="dev-page">
      <header className="dev-header">
        <div className="dev-header-left">
          <a className="dev-nav-link" href="/admin">
            <ArrowLeft size={16} /> Admin Analytics
          </a>
          <a className="dev-nav-link muted" href="/">
            Mina App
          </a>
        </div>
        <div className="dev-header-title">
          <Terminal size={22} className="accent-icon" />
          <h1>Developer Settings & Model Engine</h1>
        </div>
        <div className="dev-header-actions">
          {/* Live Auto-Save Status Indicator */}
          {saveStatus === 'saving' && (
            <span className="auto-save-indicator saving">
              <Loader2 size={13} className="spin" /> Saving changes…
            </span>
          )}
          {saveStatus === 'saved' && (
            <span className="auto-save-indicator saved">
              <CheckCircle2 size={13} /> Auto-saved
            </span>
          )}
          {saveStatus === 'error' && (
            <span className="auto-save-indicator error">
              <XCircle size={13} /> Save failed
            </span>
          )}
          <button
            type="button"
            className="dev-btn secondary"
            onClick={() => void loadSettings()}
            title="Reload settings"
          >
            <RefreshCw size={15} /> Reload
          </button>
        </div>
      </header>

      {error && (
        <div className="dev-alert error" role="alert">
          <XCircle size={18} />
          <span>{error}</span>
        </div>
      )}

      <main className="dev-grid">
        {/* Connection & Endpoint Configuration */}
        <section className={`dev-card ${isLlamaCpp ? 'llama-card-mode' : ''}`}>
          <div className="card-header">
            <div className="card-title-group">
              <Wifi size={18} className="icon-blue" />
              <h2>LLM API Connection & Endpoint</h2>
            </div>
            <div className="endpoint-toggle-container">
              <span className={`toggle-state-label ${!isLlamaCpp ? 'active' : ''}`}>
                Remote API
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={!isLlamaCpp}
                className={`dev-toggle-switch ${!isLlamaCpp ? 'on' : 'off'}`}
                onClick={() => {
                  if (!isLlamaCpp) {
                    // Turn off remote API -> switch to llama.cpp (Gemma 4 with thinking level = medium)
                    setSettings((prev) => ({
                      ...prev,
                      provider: 'llama_cpp',
                      base_url: 'http://localhost:8080/v1',
                      model: 'gemma-4-it',
                      thinking_level: 'medium',
                      api_key: '',
                      extra_params: '',
                    }))
                    setModelInfo(null)
                    setTestResult(null)
                  } else {
                    // Turn on remote API -> switch to openai_compatible
                    setSettings((prev) => ({
                      ...prev,
                      provider: 'openai_compatible',
                      base_url: 'https://openrouter.ai/api/v1',
                      model: '',
                      api_key: '',
                      extra_params: '',
                      thinking_level: '',
                    }))
                    setModelInfo(null)
                    setTestResult(null)
                  }
                }}
                title={!isLlamaCpp ? 'Switch to Local llama.cpp (Gemma 4)' : 'Enable Remote OpenAI-compatible API'}
              >
                <span className="dev-toggle-thumb" />
              </button>
              <span className={`toggle-state-label ${isLlamaCpp ? 'active' : ''}`}>
                Local Gemma 4
              </span>
            </div>
          </div>

          <p className="card-desc">
            {!isLlamaCpp
              ? 'Configure any OpenAI-compatible API endpoint (Base URL, Model ID, and API Key). Changes are saved automatically.'
              : 'Running on local embedded llama.cpp server with Gemma 4. Remote API endpoint is turned off.'}
          </p>

          {isLlamaCpp && (
            <div className="llama-cpp-banner">
              <Cpu size={15} className="alert-icon-blue" />
              <span>
                <strong>Local Gemma 4 Engine Active:</strong> Mina AI is configured to run Gemma 4 locally on <code>llama.cpp</code> (<code>http://localhost:8080/v1</code>) with Thinking Level set to <strong>Medium</strong>. Remote endpoint fields are disabled.
              </span>
            </div>
          )}

          <div className="form-group">
            <label htmlFor="base-url-input">
              Base URL <span className="req">*</span>
            </label>
            <input
              id="base-url-input"
              type="text"
              placeholder="https://openrouter.ai/api/v1"
              value={settings.base_url}
              disabled={isLlamaCpp}
              onChange={(e) => setSettings({ ...settings, base_url: e.target.value })}
            />
            <span className="field-hint">
              Target OpenAI-compatible base URL (e.g. <code>https://openrouter.ai/api/v1</code>, <code>https://api.openai.com/v1</code>, <code>http://localhost:11434/v1</code>)
            </span>
          </div>

          <div className="form-group">
            <div className="label-with-action">
              <label htmlFor="model-input">
                Model ID <span className="req">*</span>
              </label>
              <button
                type="button"
                className="inline-action-btn"
                onClick={() => void handleInspectModel()}
                disabled={isLlamaCpp || inspecting || !settings.base_url}
                title="Pull parameter metadata directly from the endpoint API"
              >
                {inspecting ? <Loader2 size={13} className="spin" /> : <Info size={13} />}
                {inspecting ? 'Pulling from API…' : 'Pull Parameter Info from API'}
              </button>
            </div>
            <input
              id="model-input"
              type="text"
              placeholder="Model identifier"
              value={settings.model}
              disabled={isLlamaCpp}
              onChange={(e) => setSettings({ ...settings, model: e.target.value })}
            />
            <span className="field-hint">
              Any model identifier accepted by the endpoint.
            </span>
          </div>

          {/* Model Capabilities & Parameters Pulled from API */}
          {hasModelInfoContent && modelInfo && (
            <div className="model-info-box">
              {modelInfo.not_matched_message && (
                <div className="model-not-found-banner">
                  <Info size={14} className="alert-icon-blue" />
                  <span>{modelInfo.not_matched_message}</span>
                </div>
              )}

              {modelInfo.matched && (
                <div className="model-info-row">
                  <span className="info-label">Reasoning / Thinking:</span>
                  {modelInfo.supports_thinking ? (
                    <span className="badge badge-success">
                      <Brain size={12} /> Supported by Endpoint API
                    </span>
                  ) : (
                    <span className="badge badge-muted">Not declared as reasoning model by endpoint</span>
                  )}
                </div>
              )}

              {modelInfo.context_length && (
                <div className="model-info-row">
                  <span className="info-label">Context Length:</span>
                  <span className="info-val">{modelInfo.context_length.toLocaleString()} tokens</span>
                </div>
              )}

              {/* Input Modalities from API */}
              {modelInfo.input_modalities && modelInfo.input_modalities.length > 0 && (
                <div className="model-info-row">
                  <span className="info-label">Accepted Input Types:</span>
                  <div className="param-chips">
                    {modelInfo.input_modalities.map((mod) => (
                      <span key={mod} className={`param-chip ${mod.toLowerCase() === 'audio' ? 'active' : ''}`}>
                        {mod.toUpperCase()}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Output Modalities from API */}
              {modelInfo.output_modalities && modelInfo.output_modalities.length > 0 && (
                <div className="model-info-row">
                  <span className="info-label">Output Generation Types:</span>
                  <div className="param-chips">
                    {modelInfo.output_modalities.map((mod) => (
                      <span key={mod} className={`param-chip ${mod.toLowerCase() === 'audio' ? 'active' : ''}`}>
                        {mod.toUpperCase()}
                      </span>
                    ))}
                  </div>
                </div>
              )}

              {/* Audio Input Warning / Support Banner */}
              {modelInfo.matched && (
                modelInfo.accepts_audio ? (
                  <div className="audio-modal-alert supported">
                    <Mic size={14} className="alert-icon-green" />
                    <span><strong>Audio Input Supported:</strong> Model accepts raw audio streams directly via API.</span>
                  </div>
                ) : (
                  <div className="audio-modal-alert warning">
                    <AlertTriangle size={14} className="alert-icon-amber" />
                    <span>
                      <strong>No Direct Audio Input:</strong> This model accepts <code>[{modelInfo.input_modalities?.join(', ') || 'text'}]</code>. It does <em>not</em> take raw audio streams; microphone audio is automatically converted to text before sending to this model.
                    </span>
                  </div>
                )
              )}

              {/* Audio Output Banner if supported */}
              {modelInfo.matched && modelInfo.output_modalities?.some((m) => m.toLowerCase() === 'audio') && (
                <div className="audio-modal-alert supported">
                  <Volume2 size={14} className="alert-icon-green" />
                  <span><strong>Native Speech Output Supported:</strong> Model can directly synthesize and output audio.</span>
                </div>
              )}

              {apiEfforts.length > 0 && (
                <div className="model-info-row">
                  <span className="info-label">API Reasoning Efforts:</span>
                  <div className="param-chips">
                    {apiEfforts.map((e) => (
                      <span key={e} className="param-chip active">{e}</span>
                    ))}
                  </div>
                </div>
              )}

              {hasSupportedParams && (
                <div className="model-info-row">
                  <span className="info-label">API Supported Parameters:</span>
                  <div className="param-chips">
                    {supportedParams.map((p) => (
                      <span key={p} className="param-chip">{p}</span>
                    ))}
                  </div>
                </div>
              )}

              {modelInfo.default_parameters && Object.keys(modelInfo.default_parameters).length > 0 && (
                <div className="model-info-row">
                  <span className="badge badge-success">
                    <Sparkles size={12} /> Auto-applied API recommended defaults: {JSON.stringify(modelInfo.default_parameters)}
                  </span>
                </div>
              )}
            </div>
          )}

          <div className="form-group">
            <label htmlFor="api-key-input">
              API Key
            </label>
            <div className="input-with-action">
              <input
                id="api-key-input"
                type={showApiKey ? 'text' : 'password'}
                placeholder="Bearer token / API key"
                value={settings.api_key}
                disabled={isLlamaCpp}
                onChange={(e) => setSettings({ ...settings, api_key: e.target.value })}
              />
              <button
                type="button"
                className="action-icon-btn"
                disabled={isLlamaCpp}
                onClick={() => setShowApiKey(!showApiKey)}
                title={showApiKey ? 'Hide Key' : 'Show Key'}
              >
                {showApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
              </button>
            </div>
            <span className="field-hint">
              Stored securely in database settings. Sent as <code>Authorization: Bearer &lt;key&gt;</code>.
            </span>
          </div>

          <div className="test-connection-section">
            <button
              type="button"
              className="dev-btn test-btn"
              onClick={() => void handleTestConnection()}
              disabled={testing || !settings.base_url || !settings.model}
            >
              {testing ? <Loader2 size={15} className="spin" /> : <Send size={15} />}
              {testing ? 'Testing Connection…' : (isLlamaCpp ? 'Test Local Gemma 4 Connection' : 'Test Model Connection')}
            </button>

            {testResult && (
              <div className={`test-result-box ${testResult.status}`}>
                <div className="test-result-header">
                  {testResult.status === 'ok' ? (
                    <span className="status-tag success">
                      <CheckCircle2 size={14} /> Connection Successful ({testResult.latency_ms} ms)
                    </span>
                  ) : (
                    <span className="status-tag error">
                      <XCircle size={14} /> Connection Failed
                    </span>
                  )}
                  {testResult.model && <span className="model-tag">{testResult.model}</span>}
                </div>
                {testResult.status === 'ok' && testResult.reply && (
                  <p className="test-reply-text">
                    <strong>Model response:</strong> &ldquo;{testResult.reply}&rdquo;
                  </p>
                )}
                {testResult.status === 'error' && (
                  <p className="test-error-text">{testResult.message || 'Unknown connection error'}</p>
                )}
              </div>
            )}
          </div>
        </section>

        {/* Extra Params: Dynamic Controls Based on API Metadata */}
        <section className="dev-card">
          <div className="card-header">
            <Sliders size={18} className="icon-purple" />
            <h2>LLM Extra Params</h2>
          </div>
          <p className="card-desc">
            {hasSupportedParams
              ? `Derived directly from ${settings.model || 'model'} API metadata (${supportedParams.length} supported parameters).`
              : 'Configure parameters and custom JSON extra params.'}
          </p>

          {/* Temperature */}
          {(!hasSupportedParams || supportedParams.includes('temperature')) && (
            <div className="form-group">
              <div className="slider-label">
                <label htmlFor="temp-slider">
                  Temperature {supportedParams.includes('temperature') && <span className="param-status-dot" title="Supported by API" />}
                </label>
                <span className="slider-val">{settings.temperature.toFixed(2)}</span>
              </div>
              <input
                id="temp-slider"
                type="range"
                min="0"
                max="2"
                step="0.05"
                value={settings.temperature}
                onChange={(e) => setSettings({ ...settings, temperature: parseFloat(e.target.value) })}
              />
              <div className="slider-range-labels">
                <span>0.0</span>
                <span>1.0</span>
                <span>2.0</span>
              </div>
            </div>
          )}

          {/* Reasoning Effort */}
          {apiEfforts.length > 0 ? (
            <div className="form-group">
              <div className="label-with-hint">
                <label htmlFor="thinking-level-select">Reasoning Effort (from API)</label>
                <span className="detected-badge">API Options: {apiEfforts.join(', ')}</span>
              </div>
              <select
                id="thinking-level-select"
                value={settings.thinking_level}
                onChange={(e) => setSettings({ ...settings, thinking_level: e.target.value })}
              >
                <option value="">Default (Unset)</option>
                {apiEfforts.map((lvl) => (
                  <option key={lvl} value={lvl}>
                    {lvl.toUpperCase()}
                  </option>
                ))}
              </select>
              <span className="field-hint">
                Reasoning effort levels reported directly by the model&apos;s API.
              </span>
            </div>
          ) : (supportedParams.includes('reasoning') || supportedParams.includes('reasoning_effort')) ? (
            <div className="form-group">
              <label htmlFor="thinking-level-input">Reasoning Effort / Parameter</label>
              <input
                id="thinking-level-input"
                type="text"
                placeholder="e.g. low, high, or leave empty"
                value={settings.thinking_level}
                onChange={(e) => setSettings({ ...settings, thinking_level: e.target.value })}
              />
            </div>
          ) : null}

          {/* Context History Window */}
          <div className="form-group">
            <label htmlFor="history-window-input">Chat History Window (Turns)</label>
            <input
              id="history-window-input"
              type="number"
              min="1"
              max="50"
              value={settings.chat_history_window}
              onChange={(e) => setSettings({ ...settings, chat_history_window: parseInt(e.target.value, 10) || 10 })}
            />
            <span className="field-hint">
              Number of prior messages sent per turn to maintain conversational context.
            </span>
          </div>

          {/* Custom Extra Parameters JSON */}
          <div className="form-group">
            <label htmlFor="extra-params-textarea">Custom Extra Parameters (JSON)</label>
            <textarea
              id="extra-params-textarea"
              rows={4}
              className="extra-params-code"
              placeholder='{"top_p": 0.95, "max_tokens": 2048}'
              value={settings.extra_params}
              onChange={(e) => setSettings({ ...settings, extra_params: e.target.value })}
            />
            <span className="field-hint">
              JSON payload merged into the completion request for any parameters (e.g. <code>top_p</code>, <code>top_k</code>, <code>max_tokens</code>, <code>presence_penalty</code>).
            </span>
          </div>
        </section>

        {/* TTS Model & Voice Settings */}
        <section className={`dev-card tts-card ${isAudar ? 'llama-card-mode' : ''}`}>
          <div className="card-header">
            <div className="card-title-group">
              <Volume2 size={18} className="icon-blue" />
              <h2>Text-to-Speech (TTS) Model & Voice</h2>
            </div>
            <div className="endpoint-toggle-container">
              <span className={`toggle-state-label ${isRemoteTTS ? 'active' : ''}`}>
                Remote API
              </span>
              <button
                type="button"
                role="switch"
                aria-checked={isRemoteTTS}
                className={`dev-toggle-switch ${isRemoteTTS ? 'on' : 'off'}`}
                onClick={() => {
                  if (!isRemoteTTS) {
                    // Turn on Remote Audio API
                    setSettings((prev) => ({
                      ...prev,
                      tts_provider: 'openai',
                      tts_model: 'tts-1',
                      tts_voice: 'alloy',
                    }))
                    setTtsTestResult(null)
                  } else {
                    // Switch to Local Audar Engine
                    setSettings((prev) => ({
                      ...prev,
                      tts_provider: 'audar',
                      tts_model: 'audarai/Audar-TTS-V1-Flash',
                      tts_voice: 'demo_female_1',
                      tts_speed: 1.0,
                    }))
                    setTtsTestResult(null)
                  }
                }}
                title={!isRemoteTTS ? 'Enable Remote Audio API (/audio/speech)' : 'Switch to Local Audar Engine'}
              >
                <span className="dev-toggle-thumb" />
              </button>
              <span className={`toggle-state-label ${isAudar ? 'active' : ''}`}>
                Local Audar
              </span>
            </div>
          </div>

          <p className="card-desc">
            {isAudar
              ? 'Running on local neural Audar engine with NeuCodec. Speech rate and voice profile are customizable.'
              : isRemoteTTS
              ? 'Routing audio synthesis to remote OpenAI-compatible /audio/speech endpoint.'
              : 'Voice synthesis disabled.'}
          </p>

          {isAudar && (
            <div className="llama-cpp-banner">
              <Volume2 size={15} className="alert-icon-blue" />
              <span>
                <strong>Local Audar Engine Active:</strong> Mina AI runs <code>Audar-TTS-V1-Flash</code> locally (24kHz low-latency streaming neural synthesis with inline emotion tags).
              </span>
            </div>
          )}

          {/* TTS Base URL Input */}
          {!isAudar && (
            <div className="form-group">
              <label htmlFor="tts-base-url-input">
                TTS Base URL <span className="req">*</span>
              </label>
              <input
                id="tts-base-url-input"
                type="text"
                placeholder="https://openrouter.ai/api/v1"
                value={settings.tts_base_url}
                onChange={(e) => setSettings({ ...settings, tts_base_url: e.target.value })}
              />
              <span className="field-hint">
                Target OpenAI-compatible audio endpoint (defaults to <code>https://openrouter.ai/api/v1</code>).
              </span>
            </div>
          )}

          {/* TTS API Key Input */}
          {!isAudar && (
            <div className="form-group">
              <div className="label-with-action">
                <label htmlFor="tts-api-key-input">TTS API Key</label>
                {settings.api_key && settings.tts_api_key !== settings.api_key && (
                  <button
                    type="button"
                    className="inline-action-btn"
                    onClick={() => setSettings((prev) => ({ ...prev, tts_api_key: prev.api_key }))}
                    title="Copy API key from LLM section above"
                  >
                    <Key size={13} /> Use LLM API Key
                  </button>
                )}
              </div>
              <div className="input-with-action">
                <input
                  id="tts-api-key-input"
                  type={showTtsApiKey ? 'text' : 'password'}
                  placeholder={
                    settings.api_key
                      ? 'Leave blank to use LLM API Key above, or enter separate key'
                      : 'Bearer token / API key for TTS endpoint'
                  }
                  value={settings.tts_api_key}
                  onChange={(e) => setSettings({ ...settings, tts_api_key: e.target.value })}
                />
                <button
                  type="button"
                  className="action-icon-btn"
                  onClick={() => setShowTtsApiKey(!showTtsApiKey)}
                  title={showTtsApiKey ? 'Hide Key' : 'Show Key'}
                >
                  {showTtsApiKey ? <EyeOff size={16} /> : <Eye size={16} />}
                </button>
              </div>
              <span className="field-hint">
                {settings.tts_api_key
                  ? 'Using separate dedicated TTS API key.'
                  : settings.api_key
                  ? 'Blank: Mina AI automatically uses the LLM API Key configured above.'
                  : 'Bearer token sent in Authorization header to the TTS endpoint.'}
              </span>
            </div>
          )}

          <div className="form-group">
            <div className="label-with-action">
              <label htmlFor="tts-model-input">TTS Model ID / Checkpoint</label>
              {!isAudar && (
                <button
                  type="button"
                  className="inline-action-btn"
                  onClick={() => void handleInspectTTSModel()}
                  disabled={inspectingTTS || !(settings.tts_base_url || settings.base_url) || !settings.tts_model}
                  title="Pull TTS capabilities and supported voices directly from the endpoint API"
                >
                  {inspectingTTS ? <Loader2 size={13} className="spin" /> : <Info size={13} />}
                  {inspectingTTS ? 'Pulling TTS Info…' : 'Pull TTS Info from API'}
                </button>
              )}
            </div>
            <input
              id="tts-model-input"
              type="text"
              placeholder="e.g. deepgram/flux-tts:free, tts-1"
              value={settings.tts_model}
              disabled={isAudar}
              onChange={(e) => setSettings({ ...settings, tts_model: e.target.value })}
            />
            <span className="field-hint">
              Target TTS model identifier accepted by endpoint (e.g. <code>deepgram/flux-tts:free</code>, <code>tts-1</code>).
            </span>
          </div>

          {/* TTS Model Capabilities Pulled from API */}
          {ttsModelInfo && ttsModelInfo.status === 'ok' && !isAudar && (
            <div className="model-info-box tts-info-box">
              <div className="model-info-row">
                <span className="info-label">API Provider:</span>
                <span className="badge badge-success">
                  <Volume2 size={12} /> {ttsModelInfo.provider_name || 'OpenAI-Compatible Audio API'}
                </span>
              </div>
              <div className="model-info-row">
                <span className="info-label">Output Audio Format:</span>
                <span className="info-val">{ttsModelInfo.format || '24 kHz WAV'}</span>
              </div>
              {ttsModelInfo.supported_voices_count ? (
                <div className="model-info-row">
                  <span className="info-label">Available API Voices:</span>
                  <span className="badge badge-muted">
                    {ttsModelInfo.supported_voices_count} Voice Models Available
                  </span>
                </div>
              ) : null}
              {ttsModelInfo.default_voice && (
                <div className="model-info-row">
                  <span className="badge badge-success">
                    <Sparkles size={12} /> Recommended Default Voice: <code>{ttsModelInfo.default_voice}</code>
                  </span>
                </div>
              )}
            </div>
          )}

          <div className="form-group">
            {isAudar ? (
              <>
                <label htmlFor="tts-voice-select">Local Reference Voice Profile (Zero-Shot Audio)</label>
                {voices.length > 0 ? (
                  <select
                    id="tts-voice-select"
                    value={settings.tts_voice}
                    onChange={(e) => setSettings({ ...settings, tts_voice: e.target.value })}
                  >
                    {voices.map((v) => (
                      <option key={v.id} value={v.id}>
                        {v.desc} ({v.id})
                      </option>
                    ))}
                  </select>
                ) : (
                  <input
                    id="tts-voice-input"
                    type="text"
                    placeholder="e.g. demo_female_1, Najdi, EGY"
                    value={settings.tts_voice}
                    onChange={(e) => setSettings({ ...settings, tts_voice: e.target.value })}
                  />
                )}
                <span className="field-hint">
                  Audar uses reference WAV audio files from assets/voices/ to clone speaker pitch, dialect, and persona.
                </span>
              </>
            ) : (
              <>
                <div className="label-with-action">
                  <label htmlFor="tts-voice-input">Remote API Voice Name / Identifier</label>
                  <button
                    type="button"
                    className="inline-action-btn"
                    onClick={() => void handleFetchRemoteVoices()}
                    disabled={fetchingVoices || !(settings.tts_base_url || settings.base_url)}
                    title="Query available voices directly from the remote endpoint API"
                  >
                    {fetchingVoices ? <Loader2 size={13} className="spin" /> : <Info size={13} />}
                    {fetchingVoices ? 'Pulling Voices from API…' : 'Pull Voices from API'}
                  </button>
                </div>
                <input
                  id="tts-voice-input"
                  type="text"
                  placeholder="e.g. flux-alexis-en, alloy, etc."
                  value={settings.tts_voice}
                  onChange={(e) => setSettings({ ...settings, tts_voice: e.target.value })}
                />

                {remoteApiVoices.length > 0 && (
                  <div className="api-voices-container">
                    {remoteApiVoices.length > 6 && (
                      <div className="voice-search-box">
                        <Search size={13} className="search-icon" />
                        <input
                          type="text"
                          className="voice-search-input"
                          placeholder={`Filter among ${remoteApiVoices.length} API voices…`}
                          value={voiceSearch}
                          onChange={(e) => setVoiceSearch(e.target.value)}
                        />
                      </div>
                    )}
                    <div className="param-chips scrollable-voices">
                      {remoteApiVoices
                        .filter((v) =>
                          voiceSearch.trim()
                            ? v.id.toLowerCase().includes(voiceSearch.toLowerCase()) ||
                              v.name.toLowerCase().includes(voiceSearch.toLowerCase())
                            : true
                        )
                        .map((v) => (
                          <button
                            key={v.id}
                            type="button"
                            className={`param-chip voice-chip ${settings.tts_voice === v.id ? 'active' : ''}`}
                            onClick={() => setSettings({ ...settings, tts_voice: v.id })}
                            title={v.id}
                          >
                            {v.name || v.id}
                          </button>
                        ))}
                    </div>
                  </div>
                )}
                <span className="field-hint">
                  {voiceFetchMsg || 'Remote OpenAI-compatible /audio/speech endpoints use named voice models.'}
                </span>
              </>
            )}
          </div>

          <div className="form-group">
            <div className="slider-label">
              <label htmlFor="tts-speed-slider">Speech Speed Multiplier</label>
              <span className="slider-val">{settings.tts_speed.toFixed(2)}x</span>
            </div>
            <input
              id="tts-speed-slider"
              type="range"
              min="0.5"
              max="2.0"
              step="0.05"
              value={settings.tts_speed}
              onChange={(e) => setSettings({ ...settings, tts_speed: parseFloat(e.target.value) })}
            />
            <div className="slider-range-labels">
              <span>0.5x (Slow)</span>
              <span>1.0x (Normal)</span>
              <span>2.0x (Fast)</span>
            </div>
          </div>

          <div className="tts-test-section">
            <label htmlFor="tts-test-phrase">Test Voice Synthesis Phrase</label>
            <div className="tts-test-input-row">
              <input
                id="tts-test-phrase"
                type="text"
                value={ttsTestPhrase}
                onChange={(e) => setTtsTestPhrase(e.target.value)}
                placeholder="Enter sample sentence in Arabic or English..."
              />
              <button
                type="button"
                className="dev-btn tts-btn"
                onClick={() => void handleTestTTS()}
                disabled={testingTTS || settings.tts_provider === 'disabled'}
              >
                {testingTTS ? <Loader2 size={15} className="spin" /> : <Play size={15} />}
                {testingTTS ? 'Synthesizing…' : 'Synthesize & Play'}
              </button>
            </div>

            {ttsTestResult && (
              <div className={`test-result-box ${ttsTestResult.status}`}>
                {ttsTestResult.status === 'ok' && ttsTestResult.audio_b64 ? (
                  <div className="tts-audio-player">
                    <span className="status-tag success">
                      <CheckCircle2 size={14} /> Synthesized ({ttsTestResult.latency_ms} ms)
                    </span>
                    <audio controls autoPlay src={ttsTestResult.audio_b64} className="tts-audio-elem" />
                  </div>
                ) : (
                  <p className="test-error-text">{ttsTestResult.message || 'Synthesis failed'}</p>
                )}
              </div>
            )}
          </div>
        </section>

        {/* System Prompt Customization */}
        <section className="dev-card system-prompt-card">
          <div className="card-header">
            <Cpu size={18} className="icon-green" />
            <h2>System Prompt</h2>
          </div>
          <p className="card-desc">
            Define Mina AI&apos;s behavior, language rules, tone, and character persona.
          </p>

          <div className="form-group">
            <textarea
              className="system-prompt-textarea"
              rows={7}
              placeholder="Enter system prompt instructions..."
              value={settings.system_prompt}
              onChange={(e) => setSettings({ ...settings, system_prompt: e.target.value })}
            />
          </div>
        </section>
      </main>
    </div>
  )
}

export default DevPage
