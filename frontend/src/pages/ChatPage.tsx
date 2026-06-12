import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import {
  getProfile, sendMessage, listChatMessages, type Profile, type ChatMessage,
  getConfigStatus, getSufficiency, type ConfigStatus, type DataSufficiency,
  getMem0Status, type Mem0Status,
  getVectorStatus, type VectorStatus,
  type ChatMode,
} from '../api/client'

const MODE_OPTIONS: { value: ChatMode; label: string; desc: string }[] = [
  { value: 'daily_chat', label: '日常闲聊', desc: '自然简短的日常对话' },
  { value: 'deep_analysis', label: '深入分析', desc: '更结构化的分析和解释' },
  { value: 'comfort', label: '安慰陪伴', desc: '先共情再给建议' },
  { value: 'advice', label: '模拟建议', desc: '基于资料的模拟建议' },
  { value: 'style_clone', label: '风格复刻', desc: '重点模仿语气和句式' },
  { value: 'communication_strategy', label: '沟通策略', desc: '良性沟通建议' },
]

function safeContent(content: string): string {
  const trimmed = content.trim()
  if ((trimmed.startsWith('{') || trimmed.startsWith('[')) && trimmed.length > 100) {
    try {
      JSON.parse(trimmed)
      return '```json\n' + trimmed + '\n```'
    } catch { /* not valid JSON */ }
  }
  return content
}

function relationshipLabel(t: string): string {
  const map: Record<string, string> = {
    friend: '朋友', family: '亲人', colleague: '同事',
    lover: '伴侣/白月光', public_figure: '公众人物',
    author: '作者/IP', celebrity: '知名人物', other: '其他',
  }
  return map[t] || t
}

export default function ChatPage() {
  const { id } = useParams<{ id: string }>()
  const profileId = Number(id)
  const isValidId = id && Number.isFinite(profileId) && profileId > 0

  const [profile, setProfile] = useState<Profile | null>(null)
  const [messages, setMessages] = useState<ChatMessage[]>([])
  const [configStatus, setConfigStatus] = useState<ConfigStatus | null>(null)
  const [sufficiency, setSufficiency] = useState<DataSufficiency | null>(null)
  const [mem0Status, setMem0Status] = useState<Mem0Status | null>(null)
  const [vectorStatus, setVectorStatus] = useState<VectorStatus | null>(null)
  const [lastRetrievalMethod, setLastRetrievalMethod] = useState<'vector' | 'keyword' | ''>('')
  const [mode, setMode] = useState<ChatMode>('daily_chat')
  const [input, setInput] = useState('')
  const [sending, setSending] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(true)
  const messagesEndRef = useRef<HTMLDivElement>(null)

  const initChat = useCallback(async () => {
    if (!isValidId) return
    try {
      setLoading(true)
      const [p, msgs, cfg, suff, m0, vector] = await Promise.all([
        getProfile(profileId),
        listChatMessages(profileId),
        getConfigStatus().catch(() => null),
        getSufficiency(profileId).catch(() => null),
        getMem0Status().catch(() => null),
        getVectorStatus(profileId).catch(() => null),
      ])
      setProfile(p)
      setMessages(msgs)
      setConfigStatus(cfg)
      setSufficiency(suff)
      setMem0Status(m0)
      setVectorStatus(vector)
    } catch (e: any) {
      setError(`请求人物 ${profileId} 失败: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }, [profileId])

  useEffect(() => { initChat() }, [initChat])

  useEffect(() => {
    messagesEndRef.current?.scrollIntoView({ behavior: 'smooth' })
  }, [messages])

  const handleSend = async () => {
    const text = input.trim()
    if (!text || sending) return
    setInput('')
    setError('')

    // Optimistic user message
    const userMsg: ChatMessage = {
      id: Date.now(),
      profile_id: profileId,
      role: 'user',
      content: text,
      created_at: new Date().toISOString(),
    }
    setMessages(prev => [...prev, userMsg])

    try {
      setSending(true)
      const result = await sendMessage(profileId, text, mode)
      setLastRetrievalMethod(result.retrieval_method || '')
      const assistantMsg: ChatMessage = {
        id: Date.now() + 1,
        profile_id: profileId,
        role: 'assistant',
        content: result.reply,
        created_at: new Date().toISOString(),
      }
      setMessages(prev => [...prev, assistantMsg])
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSending(false)
    }
  }

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === 'Enter' && !e.shiftKey) {
      e.preventDefault()
      handleSend()
    }
  }

  // Guards
  if (!isValidId) {
    return (
      <div>
        <div className="alert alert-error">
          <p><strong>无效的人物 ID</strong></p>
          <p>当前 URL 中的 ID 为: <code>{id || '(空)'}</code></p>
        </div>
        <div style={{ marginTop: '1rem' }}>
          <Link to="/profiles" className="btn-primary">返回人物列表</Link>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div className="empty-state">
        <div className="spinner" style={{ margin: '0 auto' }} />
        <p style={{ marginTop: '0.5rem' }}>加载对话中...</p>
      </div>
    )
  }

  if (error && !profile) {
    return (
      <div>
        <div className="alert alert-error">
          <p><strong>加载失败</strong></p>
          <p>人物 ID: {profileId}</p>
          <p>{error}</p>
        </div>
        <div style={{ marginTop: '1rem', display: 'flex', gap: '0.5rem' }}>
          <button className="btn-primary" onClick={initChat}>重试</button>
          <Link to="/profiles" className="btn-primary" style={{ background: 'var(--c-text-muted)', borderColor: 'var(--c-text-muted)' }}>返回人物列表</Link>
        </div>
      </div>
    )
  }

  if (!profile) {
    return (
      <div>
        <div className="alert alert-error">
          <p><strong>人物档案不存在</strong></p>
          <p>人物 ID {profileId} 在后端数据库中未找到。</p>
        </div>
        <div style={{ marginTop: '1rem' }}>
          <Link to="/profiles" className="btn-primary">返回人物列表</Link>
        </div>
      </div>
    )
  }

  const isLowData = sufficiency && (sufficiency.level === 'none' || sufficiency.level === 'very_low')

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1>人物模拟实验台</h1>
          <p>基于资料检索、画像风格卡和聊天模式进行受控模拟。</p>
        </div>
        <Link to={`/profiles/${profile.id}`} className="btn-secondary">返回档案详情</Link>
      </div>

      <div className="warning-panel">
        <strong>合规边界：</strong>此 AI 角色是基于资料生成的模拟，并非本人意识，不代表本人真实意愿。
        对话中 AI 不会冒充真人、不会生成欺骗性内容、不会伪造授权或做出法律/医疗/财务决定。
      </div>

      <div className="chat-layout">
        {/* Sidebar */}
        <div className="chat-sidebar">
          <div className="card">
            <div className="profile-summary">
              <h3>{profile.name}</h3>
              <p style={{ color: 'var(--muted)', fontSize: '0.86rem', marginBottom: '0.75rem' }}>
                {profile.description || '暂无描述'}
              </p>
              <div className="status-row">
                <span className="badge">{relationshipLabel(profile.relationship_type)}</span>
                <span className={profile.has_analysis ? 'badge badge-success' : 'badge badge-muted'}>
                  {profile.has_analysis ? '有画像' : '未分析'}
                </span>
              </div>
              <div className="quality-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.5rem', marginTop: '0.85rem' }}>
                <div className="metric-card">
                  <div className="metric-label">Files</div>
                  <div className="metric-value">{profile.document_count}</div>
                </div>
                <div className="metric-card">
                  <div className="metric-label">Chunks</div>
                  <div className="metric-value">{profile.chunk_count}</div>
                </div>
              </div>

              {/* Data Sufficiency */}
              {sufficiency && (
                <div style={{ marginTop: '0.85rem' }}>
                  <div className="sufficiency-bar" style={{ marginTop: '0.25rem' }}>
                    <div className="sufficiency-head">
                      <span>资料充分度</span>
                      <span>{sufficiency.label}</span>
                    </div>
                    <div className="bar-track">
                      <div className={`bar-fill ${sufficiency.level}`} />
                    </div>
                  </div>
                </div>
              )}

              {/* Provider Badge */}
              {configStatus && (
                <div style={{ marginTop: '0.75rem', display: 'flex', alignItems: 'center', gap: '0.5rem' }}>
                  <span className={`badge chat-provider-badge ${configStatus.is_mock ? 'mock' : 'deepseek'}`}>
                    Provider · {configStatus.is_mock ? 'Mock 演示' : configStatus.llm_provider}
                  </span>
                </div>
              )}

              {/* mem0 Status Badge */}
              {mem0Status && (
                <div style={{ marginTop: '0.5rem' }}>
                  <span className={`badge chat-provider-badge ${mem0Status.available ? 'deepseek' : 'mock'}`}>
                    {mem0Status.available ? '记忆增强已启用' : '记忆增强可选'}
                  </span>
                </div>
              )}

              {/* RAG Retrieval Status */}
              {vectorStatus && (
                <div className="subtle-panel retrieval-mini">
                  <div className="sufficiency-head" style={{ marginBottom: '0.35rem' }}>
                    <span>RAG 检索方式</span>
                    <span className={vectorStatus.available ? 'badge badge-success' : 'badge badge-muted'}>
                      {vectorStatus.available ? '语义增强' : '基础检索'}
                    </span>
                  </div>
                  <p style={{ color: 'var(--muted)', fontSize: '0.75rem' }}>
                    {vectorStatus.available
                      ? '当前会优先参考语义证据检索，并保留基础检索兜底。'
                      : '当前使用基础检索。资料量较大时，管理员可启用语义检索增强。'}
                  </p>
                  {lastRetrievalMethod && (
                    <span className="badge badge-info">上次回复: {lastRetrievalMethod}</span>
                  )}
                </div>
              )}

              {/* Current mode display */}
              <div className="subtle-panel" style={{ marginTop: '0.85rem' }}>
                <p style={{ fontSize: '0.8rem' }}>
                  <strong>当前模式：</strong>{MODE_OPTIONS.find(m => m.value === mode)?.label}
                </p>
                <p style={{ fontSize: '0.75rem', color: 'var(--muted)' }}>
                  {MODE_OPTIONS.find(m => m.value === mode)?.desc}
                </p>
              </div>

              {/* Low data warning */}
              {isLowData && (
                <div className="chat-data-warning">
                  <strong>提醒：</strong>当前资料较少，AI 回复可能更像推断而非稳定复刻。
                  {sufficiency?.level === 'none' && ' 建议先上传资料文件。'}
                  {sufficiency?.level === 'very_low' && ' 建议上传更多资料（至少 2000 字）以获得更稳定的模拟效果。'}
                </div>
              )}

              {/* No analysis warning */}
              {!profile.has_analysis && (
                <div className="no-data-warning">
                  {profile.chunk_count === 0
                    ? '尚未上传资料，对话将使用默认风格。建议先上传资料并生成画像。'
                    : '尚未分析，对话将使用默认风格卡。点击"重新分析"按钮生成画像。'}
                </div>
              )}

              {/* Has analysis but no data warning */}
              {profile.has_analysis && profile.chunk_count === 0 && (
                <div className="no-data-warning" style={{ background: '#fef2f2', border: '1px solid #fecaca', color: 'var(--c-danger)' }}>
                  <strong>提醒：</strong>当前为默认模拟角色，AI 回复不代表人物真实风格。
                </div>
              )}
            </div>
          </div>
        </div>

        {/* Chat Window */}
        <div className="chat-window">
          {/* Mode Selector */}
          <div className="mode-selector">
            {MODE_OPTIONS.map(m => (
              <button
                key={m.value}
                className={mode === m.value ? 'active' : ''}
                onClick={() => setMode(m.value)}
                title={m.desc}
              >
                {m.label}
              </button>
            ))}
          </div>

          <div className="chat-messages">
            {messages.length === 0 && (
              <div className="empty-state" style={{ padding: '2rem' }}>
                <h3>开始对话</h3>
                <p style={{ fontSize: '0.85rem', marginBottom: '0.5rem' }}>
                  基于 {profile.name} 的资料进行对话。
                </p>
                <p style={{ fontSize: '0.8rem', color: 'var(--c-text-muted)' }}>
                  上方可切换对话模式：日常闲聊、深入分析、安慰陪伴、模拟建议、风格复刻、沟通策略
                </p>
              </div>
            )}
            {messages.map(msg => (
              <div key={msg.id} className={`chat-msg ${msg.role}`}>
                {msg.role === 'user' ? (
                  msg.content
                ) : (
                  <ReactMarkdown>{safeContent(msg.content)}</ReactMarkdown>
                )}
              </div>
            ))}
            {sending && (
              <div className="chat-msg assistant">
                <span className="spinner" />
              </div>
            )}
            {error && (
              <div className="chat-msg assistant" style={{ background: '#fef2f2', border: '1px solid #fecaca' }}>
                {error}
              </div>
            )}
            <div ref={messagesEndRef} />
          </div>
          <div className="chat-input-area">
            <textarea
              value={input}
              onChange={e => setInput(e.target.value)}
              onKeyDown={handleKeyDown}
              placeholder="输入消息，Enter 发送，Shift+Enter 换行"
              disabled={sending}
              rows={3}
            />
            <button className="btn-primary" onClick={handleSend} disabled={sending || !input.trim()}>
              发送
            </button>
          </div>
        </div>
      </div>
    </div>
  )
}
