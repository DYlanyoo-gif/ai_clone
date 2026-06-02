import { useState, useEffect, useRef, useCallback } from 'react'
import { useParams, Link } from 'react-router-dom'
import ReactMarkdown from 'react-markdown'
import {
  getProfile, uploadDocument, listDocuments,
  analyzeProfile, type Profile, type Document,
  getConfigStatus, exportSkillCard, exportDataset,
  getSufficiency, type DataSufficiency, type ConfigStatus,
  getMineruStatus, type MineruStatus,
} from '../api/client'

// Parse Markdown into sections by H2 headers
function parseMarkdownSections(md: string): { title: string; content: string; anchor: string }[] {
  if (!md) return []
  // Remove the top-level H1 and compliance blockquote
  const body = md.replace(/^# .*\n/, '').replace(/^> .*\n/gm, '').trim()
  // Split on "## N. " pattern
  const sections = body.split(/\n(?=## \d+\. )/)
  return sections.map(s => {
    const match = s.match(/^## (\d+\. .+)/)
    const title = match ? match[1] : s.split('\n')[0].replace(/^## /, '')
    const anchor = title.replace(/[^\w一-鿿]/g, '-').replace(/-+/g, '-').toLowerCase()
    return { title, content: s.trim(), anchor }
  }).filter(s => s.title)
}

// Parse style card sections similarly
function parseStyleCardSections(md: string): { title: string; content: string; anchor: string }[] {
  if (!md) return []
  const sections = md.split(/\n(?=## \d+\. )/)
  return sections.map(s => {
    const title = s.split('\n')[0].replace(/^## /, '')
    const anchor = title.replace(/[^\w一-鿿]/g, '-').replace(/-+/g, '-').toLowerCase()
    return { title, content: s.trim(), anchor }
  }).filter(s => s.title)
}

function relationshipLabel(t: string): string {
  const map: Record<string, string> = {
    friend: '朋友', family: '亲人', colleague: '同事',
    lover: '伴侣/白月光', public_figure: '公众人物',
    author: '作者/IP', celebrity: '知名人物', other: '其他',
  }
  return map[t] || t
}

export default function ProfileDetailPage() {
  const { id } = useParams<{ id: string }>()
  const profileId = Number(id)
  const isValidId = id && Number.isFinite(profileId) && profileId > 0

  const [profile, setProfile] = useState<Profile | null>(null)
  const [documents, setDocuments] = useState<Document[]>([])
  const [configStatus, setConfigStatus] = useState<ConfigStatus | null>(null)
  const [mineruStatus, setMineruStatus] = useState<MineruStatus | null>(null)
  const [sufficiency, setSufficiency] = useState<DataSufficiency | null>(null)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [success, setSuccess] = useState('')
  const [analyzing, setAnalyzing] = useState(false)
  const [uploading, setUploading] = useState(false)
  const [exporting, setExporting] = useState('')
  const [copied, setCopied] = useState('')
  const [activeSection, setActiveSection] = useState('')
  const [uploadingFileName, setUploadingFileName] = useState('')
  const fileInputRef = useRef<HTMLInputElement>(null)

  const fetchData = useCallback(async () => {
    if (!isValidId) return
    try {
      setLoading(true)
      setError('')
      const [p, docs, cfg, mineru, suff] = await Promise.all([
        getProfile(profileId),
        listDocuments(profileId),
        getConfigStatus().catch(() => null),
        getMineruStatus().catch(() => null),
        getSufficiency(profileId).catch(() => null),
      ])
      setProfile(p)
      setDocuments(docs)
      setConfigStatus(cfg)
      setMineruStatus(mineru)
      setSufficiency(suff)
    } catch (e: any) {
      setError(`请求人物 ${profileId} 详情失败: ${e.message}`)
    } finally {
      setLoading(false)
    }
  }, [profileId])

  useEffect(() => { fetchData() }, [fetchData])

  // Scrollspy for TOC
  useEffect(() => {
    const handleScroll = () => {
      const anchors = document.querySelectorAll('.section-anchor')
      let current = ''
      anchors.forEach(el => {
        const rect = el.getBoundingClientRect()
        if (rect.top <= 120) current = el.id
      })
      if (current) setActiveSection(current)
    }
    window.addEventListener('scroll', handleScroll, { passive: true })
    return () => window.removeEventListener('scroll', handleScroll)
  }, [profile?.latest_portrait])

  const allowedExtensions = [
    '.txt', '.md', '.markdown', '.json', '.csv',
    '.pdf', '.docx', '.pptx', '.xlsx', '.png', '.jpg', '.jpeg', '.webp',
  ]
  const mineruExtensions = ['.pdf', '.docx', '.pptx', '.xlsx', '.png', '.jpg', '.jpeg', '.webp']
  const isMineruFile = (name: string) => mineruExtensions.some(ext => name.toLowerCase().endsWith(ext))

  const handleUpload = async (files: FileList | null) => {
    if (!files || files.length === 0) return
    const file = files[0]
    if (!allowedExtensions.some(ext => file.name.toLowerCase().endsWith(ext))) {
      setError('不支持的文件格式，请上传 ' + allowedExtensions.join(' / '))
      return
    }
    // Check MinerU requirement for complex files
    if (isMineruFile(file.name)) {
      if (!mineruStatus?.installed) {
        setError(
          '当前未安装 MinerU，无法解析 PDF/DOCX/PPTX/XLSX/图片文件。' +
          '请先运行: powershell -ExecutionPolicy Bypass -File scripts/install_mineru_windows.ps1，' +
          '或上传 txt/md/json/csv 文件。'
        )
        return
      }
      if (!mineruStatus?.enabled) {
        setError('MinerU 已安装但未启用。请在 .env 中设置 MINERU_ENABLED=true')
        return
      }
    }
    try {
      setUploading(true)
      setUploadingFileName(file.name)
      setError('')
      setSuccess('')
      await uploadDocument(profileId, file)
      setSuccess(`文件 "${file.name}" 上传成功`)
      await fetchData()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setUploading(false)
      setUploadingFileName('')
    }
  }

  const handleAnalyze = async () => {
    try {
      setAnalyzing(true)
      setError('')
      setSuccess('')
      await analyzeProfile(profileId)
      setSuccess('深度分析完成！')
      await fetchData()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setAnalyzing(false)
    }
  }

  const handleExportSkillCard = async () => {
    try {
      setExporting('skill-card')
      setError('')
      const result = await exportSkillCard(profileId)
      const blob = new Blob([result.content], { type: 'text/markdown;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = result.filename; a.click()
      URL.revokeObjectURL(url)
      setSuccess('Skill Card 已导出')
    } catch (e: any) {
      setError(e.message)
    } finally {
      setExporting('')
    }
  }

  const handleExportDataset = async () => {
    try {
      setExporting('dataset')
      setError('')
      const result = await exportDataset(profileId)
      const jsonStr = JSON.stringify(result.records, null, 2)
      const blob = new Blob([jsonStr], { type: 'application/json;charset=utf-8' })
      const url = URL.createObjectURL(blob)
      const a = document.createElement('a')
      a.href = url; a.download = result.filename; a.click()
      URL.revokeObjectURL(url)
      setSuccess(`数据集已导出，共 ${result.total_records} 条记录`)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setExporting('')
    }
  }

  const handleCopyStyleCard = () => {
    if (profile?.latest_style_card) {
      navigator.clipboard.writeText(profile.latest_style_card).then(() => {
        setCopied('style-card')
        setTimeout(() => setCopied(''), 2000)
      })
    }
  }

  // Guards
  if (!isValidId) {
    return (
      <div>
        <div className="alert alert-error">
          <p><strong>无效的人物 ID</strong></p>
          <p>当前 URL 中的 ID 为: <code>{id || '(空)'}</code>，不是有效的人物 ID。</p>
        </div>
        <div style={{ marginTop: '1rem' }}>
          <Link to="/profiles" className="btn-primary">返回人物列表</Link>
        </div>
      </div>
    )
  }

  if (loading) {
    return (
      <div>
        <div className="empty-state">
          <div className="spinner" style={{ margin: '0 auto' }} />
          <p style={{ marginTop: '0.5rem' }}>加载人物 {profileId} 详情中...</p>
        </div>
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
          <button className="btn-primary" onClick={fetchData}>重试</button>
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
          <p>人物 ID {profileId} 在后端数据库中未找到，可能已被删除。</p>
        </div>
        <div style={{ marginTop: '1rem' }}>
          <Link to="/profiles" className="btn-primary">返回人物列表</Link>
        </div>
      </div>
    )
  }

  const portraitSections = parseMarkdownSections(profile.latest_portrait || '')
  const styleSections = parseStyleCardSections(profile.latest_style_card || '')

  return (
    <div>
      {/* ── Header Card ── */}
      <div className="profile-header-card">
        <h1>{profile.name}</h1>
        <div className="header-meta">
          <span>{relationshipLabel(profile.relationship_type)}</span>
          {profile.description && <span>{profile.description}</span>}
        </div>
        <div className="header-stats">
          <span>📄 {profile.document_count} 文件</span>
          <span>📝 {profile.chunk_count} 片段</span>
          <span>📊 {profile.total_chars?.toLocaleString() || 0} 字符</span>
          {configStatus && (
            <>
              <span>🔧 {configStatus.is_mock ? 'Mock 演示' : configStatus.llm_provider}</span>
              <span>🤖 分析: {configStatus.analysis_model}</span>
              <span>💬 聊天: {configStatus.chat_model}</span>
            </>
          )}
        </div>
        <div className="header-actions">
          <Link to={`/profiles/${profile.id}/chat`}>开始对话</Link>
          <button
            onClick={handleAnalyze}
            disabled={analyzing || profile.chunk_count === 0}
          >
            {analyzing ? '分析中...' : '重新分析'}
          </button>
        </div>
      </div>

      {error && <div className="alert alert-error" style={{ cursor: 'pointer' }} onClick={() => setError('')}>{error} (点击关闭)</div>}
      {success && <div className="alert alert-success" style={{ cursor: 'pointer' }} onClick={() => setSuccess('')}>{success} (点击关闭)</div>}

      {/* ── Upload Card ── */}
      <div className="card" style={{ marginBottom: '1.5rem' }}>
        <h2 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>上传资料</h2>

        {/* MinerU Status Banner */}
        {mineruStatus && (
          <div className={`mineru-status-banner ${mineruStatus.installed && mineruStatus.enabled ? 'mineru-ready' : 'mineru-missing'}`}>
            {mineruStatus.installed && mineruStatus.enabled ? (
              <div>
                <span>MinerU 文档解析已启用 ({mineruStatus.command})</span>
                <span style={{ marginLeft: '0.75rem', fontSize: '0.8rem', color: 'var(--c-text-muted)' }}>
                  backend={mineruStatus.backend} · method={mineruStatus.method} · lang={mineruStatus.lang}
                  {mineruStatus.image_analysis && ' · 图片分析: 开'}
                </span>
                <div style={{ fontSize: '0.75rem', color: 'var(--c-text-muted)', marginTop: '2px' }}>
                  pipeline 更快更稳，hybrid-auto-engine 更强但更慢。
                  {mineruStatus.backend === 'hybrid-auto-engine' && ' 当前使用 hybrid 后端，解析大型文档可能需要数分钟。'}
                </div>
              </div>
            ) : (
              <span>复杂文档解析未启用，仅支持 txt / md / json / csv</span>
            )}
          </div>
        )}

        <div
          className={`upload-zone ${uploading ? 'dragover' : ''}`}
          onClick={() => fileInputRef.current?.click()}
          onDragOver={e => { e.preventDefault(); e.currentTarget.classList.add('dragover') }}
          onDragLeave={e => e.currentTarget.classList.remove('dragover')}
          onDrop={e => {
            e.preventDefault()
            e.currentTarget.classList.remove('dragover')
            handleUpload(e.dataTransfer.files)
          }}
        >
          {uploading ? (
            <p>
              <span className="spinner" />
              {isMineruFile(uploadingFileName)
                ? ' 正在调用 MinerU 解析，可能需要较长时间...'
                : ' 上传处理中...'}
            </p>
          ) : (
            <p>拖拽文件到此处，或点击选择文件<br />
              <span style={{ fontSize: '0.8rem', color: 'var(--c-text-muted)' }}>
                支持 txt / md / json / csv / pdf / docx / pptx / xlsx / png / jpg / webp
              </span>
            </p>
          )}
        </div>
        <input
          ref={fileInputRef}
          type="file"
          accept=".txt,.md,.markdown,.json,.csv,.pdf,.docx,.pptx,.xlsx,.png,.jpg,.jpeg,.webp"
          style={{ display: 'none' }}
          onChange={e => handleUpload(e.target.files)}
        />

        {sufficiency && (
          <div className="sufficiency-bar">
            <span className={`sufficiency-label`}>资料充分度：{sufficiency.label}</span>
            <div className="bar-track">
              <div className={`bar-fill ${sufficiency.level}`} />
            </div>
          </div>
        )}
        {sufficiency && (
          <p style={{ fontSize: '0.8rem', color: 'var(--c-text-muted)', marginBottom: '0.5rem' }}>
            {sufficiency.description}
          </p>
        )}

        {documents.length > 0 ? (
          <div className="file-list">
            <h3 style={{ fontSize: '0.9rem', marginBottom: '0.5rem' }}>
              已上传资料 ({documents.length} 个文件)
            </h3>
            {documents.map(doc => (
              <div key={doc.id} className="file-item">
                <div>
                  <span>{doc.filename}</span>
                  {doc.parser && doc.parser !== 'builtin' && (
                    <span className="badge" style={{ marginLeft: '0.5rem', fontSize: '0.7rem' }}>
                      {doc.parser}
                    </span>
                  )}
                  {doc.parse_status === 'failed' && (
                    <span className="badge" style={{ marginLeft: '0.5rem', fontSize: '0.7rem', background: '#fef2f2', color: 'var(--c-danger)' }}>
                      解析失败
                    </span>
                  )}
                </div>
                <span style={{ color: 'var(--c-text-muted)', fontSize: '0.8rem' }}>
                  {doc.char_count.toLocaleString()} 字符 · {new Date(doc.uploaded_at).toLocaleDateString('zh-CN')}
                </span>
              </div>
            ))}
          </div>
        ) : (
          <div className="empty-state" style={{ padding: '1rem' }}>
            <p style={{ fontSize: '0.85rem' }}>还没有上传任何资料</p>
          </div>
        )}
      </div>

      {/* ── Deep Portrait Dashboard ── */}
      {profile.has_analysis && portraitSections.length > 0 ? (
        <>
          <h2 style={{ fontSize: '1.2rem', marginBottom: '1rem', marginTop: '0' }}>
            深度人物画像 Dashboard
          </h2>
          <div className="dashboard-layout">
            {/* TOC */}
            <div className="dashboard-toc">
              <div className="toc-card">
                <h3>目录</h3>
                {portraitSections.map(s => (
                  <a
                    key={s.anchor}
                    href={`#${s.anchor}`}
                    className={activeSection === s.anchor ? 'active' : ''}
                    onClick={e => {
                      e.preventDefault()
                      document.getElementById(s.anchor)?.scrollIntoView({ behavior: 'smooth' })
                    }}
                  >
                    {s.title}
                  </a>
                ))}
              </div>
            </div>

            {/* Dashboard Cards */}
            <div className="dashboard-grid">
              {portraitSections.map(s => (
                <div key={s.anchor} id={s.anchor} className="dashboard-card section-anchor">
                  <h3>{s.title}</h3>
                  <div className="card-body">
                    <ReactMarkdown>{s.content}</ReactMarkdown>
                  </div>
                </div>
              ))}
            </div>
          </div>
        </>
      ) : (
        <div className="card" style={{ marginBottom: '1.5rem' }}>
          <div className="empty-state">
            <h3>尚未生成分析报告</h3>
            <p>请先上传资料，然后点击"重新分析"按钮生成深度人物画像</p>
          </div>
        </div>
      )}

      {/* ── Style Card ── */}
      {profile.has_analysis && profile.latest_style_card && (
        <div className="style-card-display">
          <div style={{ display: 'flex', justifyContent: 'space-between', alignItems: 'center', marginBottom: '0.5rem' }}>
            <h2 style={{ margin: 0, border: 'none', padding: 0 }}>AI 风格卡</h2>
            <button className="copy-btn" onClick={handleCopyStyleCard}>
              {copied === 'style-card' ? '已复制 ✓' : '复制风格卡'}
            </button>
          </div>
          {styleSections.length > 0 ? (
            <div className="dashboard-grid">
              {styleSections.map(s => (
                <div key={s.anchor} className="dashboard-card">
                  <h3>{s.title}</h3>
                  <div className="card-body">
                    <ReactMarkdown>{s.content}</ReactMarkdown>
                  </div>
                </div>
              ))}
            </div>
          ) : (
            <div className="report-content">
              <ReactMarkdown>{profile.latest_style_card}</ReactMarkdown>
            </div>
          )}
        </div>
      )}

      {/* ── Export ── */}
      <div className="card" style={{ marginTop: '1rem' }}>
        <h2 style={{ fontSize: '1rem', marginBottom: '0.75rem' }}>导出</h2>
        <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
          <button
            className="btn-primary"
            onClick={handleExportSkillCard}
            disabled={!profile.has_analysis || exporting === 'skill-card'}
            style={{ fontSize: '0.85rem' }}
          >
            {exporting === 'skill-card' ? <><span className="spinner" /> 导出中</> : '导出 Skill Card'}
          </button>
          <button
            className="btn-primary"
            onClick={handleExportDataset}
            disabled={profile.chunk_count === 0 || exporting === 'dataset'}
            style={{ fontSize: '0.85rem', background: 'var(--c-text-muted)', borderColor: 'var(--c-text-muted)' }}
          >
            {exporting === 'dataset' ? <><span className="spinner" /> 导出中</> : '导出 Dataset'}
          </button>
        </div>
        {!profile.has_analysis && (
          <p style={{ fontSize: '0.8rem', color: 'var(--c-text-muted)', marginTop: '0.5rem' }}>
            Skill Card 需要先生成画像报告和风格卡
          </p>
        )}
      </div>
    </div>
  )
}
