import { useState, useEffect, useMemo, useRef } from 'react'
import { Link } from 'react-router-dom'
import { listProfiles, createProfile, type Profile } from '../api/client'

type ArchiveView = 'featured' | 'list' | 'matrix'
type ArchiveFilter = 'all' | 'analyzed' | 'runtime' | 'pending'

const VIEW_STORAGE_KEY = 'echo_profile_list_view'

export default function ProfileListPage() {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', relationship_type: 'other' })
  const [submitting, setSubmitting] = useState(false)
  const [view, setView] = useState<ArchiveView>(() => {
    if (typeof window === 'undefined') return 'featured'
    const stored = localStorage.getItem(VIEW_STORAGE_KEY)
    return stored === 'list' || stored === 'matrix' || stored === 'featured' ? stored : 'featured'
  })
  const [query, setQuery] = useState('')
  const [filter, setFilter] = useState<ArchiveFilter>('all')
  const [mobileIndex, setMobileIndex] = useState(0)
  const deckRef = useRef<HTMLDivElement>(null)

  const fetchProfiles = async () => {
    try {
      setLoading(true)
      setError('')
      const data = await listProfiles()
      setProfiles(data)
    } catch (e: any) {
      setError(e.message)
    } finally {
      setLoading(false)
    }
  }

  useEffect(() => { fetchProfiles() }, [])

  const filteredProfiles = useMemo(() => {
    const keyword = query.trim().toLowerCase()
    return profiles.filter(profile => {
      const simulationReady = isSimulationReady(profile)
      const matchesFilter =
        filter === 'all'
        || (filter === 'analyzed' && profile.has_analysis)
        || (filter === 'runtime' && simulationReady)
        || (filter === 'pending' && !profile.has_analysis)
      if (!matchesFilter) return false
      if (!keyword) return true
      return [
        profile.name,
        profile.description,
        relationshipLabel(profile.relationship_type),
        profile.relationship_type,
      ].some(value => String(value || '').toLowerCase().includes(keyword))
    })
  }, [profiles, query, filter])

  useEffect(() => {
    if (mobileIndex >= filteredProfiles.length) setMobileIndex(0)
  }, [filteredProfiles.length, mobileIndex])

  const handleCreate = async () => {
    if (!form.name.trim()) return
    try {
      setSubmitting(true)
      setError('')
      await createProfile(form)
      setShowModal(false)
      setForm({ name: '', description: '', relationship_type: 'other' })
      await fetchProfiles()
    } catch (e: any) {
      setError(e.message)
    } finally {
      setSubmitting(false)
    }
  }

  const changeView = (nextView: ArchiveView) => {
    setView(nextView)
    localStorage.setItem(VIEW_STORAGE_KEY, nextView)
  }

  const moveMobileDeck = (delta: number) => {
    if (filteredProfiles.length === 0) return
    const next = Math.max(0, Math.min(filteredProfiles.length - 1, mobileIndex + delta))
    setMobileIndex(next)
    const target = deckRef.current?.children.item(next) as HTMLElement | null
    target?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
  }

  const handleDeckScroll = () => {
    const track = deckRef.current
    const first = track?.children.item(0) as HTMLElement | null
    if (!track || !first) return
    const gap = 12
    const nextIndex = Math.round(track.scrollLeft / (first.offsetWidth + gap))
    if (nextIndex !== mobileIndex) {
      setMobileIndex(Math.max(0, Math.min(filteredProfiles.length - 1, nextIndex)))
    }
  }

  return (
    <div className="profile-list-page fade-in">
      <div className="page-header profile-library-header">
        <div>
          <span className="badge badge-info">Persona Archive</span>
          <h1>人物档案库</h1>
          <p>创建档案、上传授权资料，再生成画像和站内模拟实验台。</p>
        </div>
        <button className="btn-primary" onClick={() => setShowModal(true)}>新建人物档案</button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {!loading && profiles.length > 0 && (
        <section className="archive-toolbar glass-panel" aria-label="档案浏览器工具栏">
          <div className="archive-search">
            <input
              value={query}
              onChange={event => setQuery(event.target.value)}
              placeholder="搜索人物档案..."
              aria-label="搜索人物档案"
            />
          </div>
          <div className="archive-filter-chips" aria-label="筛选人物档案">
            {[
              { value: 'all' as const, label: '全部' },
              { value: 'analyzed' as const, label: '已完成画像' },
              { value: 'runtime' as const, label: '模拟可用' },
              { value: 'pending' as const, label: '待分析' },
            ].map(item => (
              <button
                key={item.value}
                type="button"
                className={filter === item.value ? 'active' : ''}
                onClick={() => setFilter(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
          <div className="archive-view-toggle" role="tablist" aria-label="档案视图">
            {[
              { value: 'featured' as const, label: '精选卡片' },
              { value: 'list' as const, label: '紧凑列表' },
              { value: 'matrix' as const, label: '状态矩阵' },
            ].map(item => (
              <button
                key={item.value}
                type="button"
                role="tab"
                aria-selected={view === item.value}
                className={view === item.value ? 'active' : ''}
                onClick={() => changeView(item.value)}
              >
                {item.label}
              </button>
            ))}
          </div>
        </section>
      )}

      {loading ? (
        <div className="archive-grid-compact">
          {[0, 1, 2].map(item => (
            <div className="card profile-card-skeleton" key={item}>
              <span className="skeleton skeleton-title" />
              <span className="skeleton skeleton-line" />
              <span className="skeleton skeleton-line medium" />
              <span className="skeleton skeleton-panel" />
            </div>
          ))}
        </div>
      ) : profiles.length === 0 ? (
        <div className="card empty-state profile-empty-state">
          <span className="badge badge-info">Start Here</span>
          <h3>还没有人物档案</h3>
          <p>创建第一个人物档案，上传资料后即可生成画像和模拟实验台。</p>
          <button className="btn-primary" onClick={() => setShowModal(true)}>
            创建第一个档案
          </button>
        </div>
      ) : filteredProfiles.length === 0 ? (
        <div className="card empty-state profile-empty-state">
          <span className="badge badge-muted">No Results</span>
          <h3>没有匹配的档案</h3>
          <p>调整搜索关键词或筛选条件，继续浏览已有人物档案。</p>
          <button className="btn-secondary" onClick={() => { setQuery(''); setFilter('all') }}>
            清空筛选
          </button>
        </div>
      ) : view === 'list' ? (
        <ArchiveRowList profiles={filteredProfiles} />
      ) : view === 'matrix' ? (
        <ArchiveStatusMatrix profiles={filteredProfiles} />
      ) : (
        <>
          <div className="archive-mobile-controls">
            <span>{mobileIndex + 1} / {filteredProfiles.length}</span>
            <div>
              <button className="btn-sm" type="button" onClick={() => moveMobileDeck(-1)} disabled={mobileIndex === 0}>←</button>
              <button className="btn-sm" type="button" onClick={() => moveMobileDeck(1)} disabled={mobileIndex >= filteredProfiles.length - 1}>→</button>
            </div>
          </div>
          <div className="archive-mobile-deck">
            <div className="archive-snap-track" ref={deckRef} onScroll={handleDeckScroll}>
              {filteredProfiles.map((profile) => (
                <ArchiveProfileCard profile={profile} key={profile.id} mobile />
              ))}
            </div>
            <div className="archive-dot-row" aria-label="档案位置">
              {filteredProfiles.map((profile, index) => (
                <button
                  key={profile.id}
                  type="button"
                  aria-label={`查看第 ${index + 1} 个档案`}
                  className={`archive-dot ${mobileIndex === index ? 'active' : ''}`}
                  onClick={() => {
                    setMobileIndex(index)
                    const target = deckRef.current?.children.item(index) as HTMLElement | null
                    target?.scrollIntoView({ behavior: 'smooth', inline: 'center', block: 'nearest' })
                  }}
                />
              ))}
            </div>
            <button className="btn-secondary archive-expand-list" type="button" onClick={() => changeView('list')}>
              展开为列表
            </button>
          </div>
          <div className="archive-desktop-view archive-grid-compact">
            {filteredProfiles.map((profile) => (
              <ArchiveProfileCard profile={profile} key={profile.id} />
            ))}
          </div>
        </>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowModal(false) }}>
          <div className="modal-content profile-create-modal">
            <div className="modal-header">
              <div>
                <span className="badge badge-info">New Archive</span>
                <h2>新建人物档案</h2>
                <p>先建立档案，再上传授权资料进行画像分析。</p>
              </div>
              <button className="modal-close" onClick={() => setShowModal(false)} aria-label="关闭">×</button>
            </div>
            <div className="form-group">
              <label>姓名 *</label>
              <input
                value={form.name}
                onChange={e => setForm({ ...form, name: e.target.value })}
                placeholder="输入人物姓名"
                autoFocus
              />
            </div>
            <div className="form-group">
              <label>关系类型</label>
              <select
                value={form.relationship_type}
                onChange={e => setForm({ ...form, relationship_type: e.target.value })}
              >
                <option value="other">其他</option>
                <option value="friend">朋友</option>
                <option value="family">亲人</option>
                <option value="colleague">同事</option>
                <option value="lover">伴侣/白月光</option>
                <option value="public_figure">公众人物</option>
                <option value="author">作者/IP</option>
              </select>
            </div>
            <div className="form-group">
              <label>描述</label>
              <textarea
                value={form.description}
                onChange={e => setForm({ ...form, description: e.target.value })}
                placeholder="简要描述这个人（可选）"
                rows={3}
              />
            </div>
            <div className="form-actions">
              <button className="btn-secondary" onClick={() => setShowModal(false)}>取消</button>
              <button className="btn-primary" onClick={handleCreate} disabled={submitting || !form.name.trim()}>
                {submitting ? <><span className="spinner" /> 创建中</> : '创建档案'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}

function ArchiveProfileCard({ profile, mobile = false }: { profile: Profile; mobile?: boolean }) {
  const simulationReady = isSimulationReady(profile)
  return (
    <Link to={`/profiles/${profile.id}`} className="profile-card-link">
      <article className={`archive-card compact-archive-card hover-lift ${simulationReady ? 'ready' : profile.has_analysis ? 'analyzed' : profile.document_count > 0 ? 'pending' : 'empty'} ${mobile ? 'mobile-card' : ''}`}>
        <div className="archive-status-strip" />
        <div className="archive-card-top">
          <div>
            <h3>{profile.name}</h3>
            <div className="meta archive-badge-row">
              <span className="badge badge-muted">{relationshipLabel(profile.relationship_type)}</span>
              <span className={profile.has_analysis ? 'badge badge-success' : 'badge badge-warning'}>
                {profile.has_analysis ? '画像完成' : '待分析'}
              </span>
              <span className={simulationReady ? 'badge badge-success' : 'badge badge-muted'}>
                {simulationReady ? '模拟可用' : '模拟未备'}
              </span>
            </div>
          </div>
          <span className="archive-open-indicator">打开</span>
        </div>

        <p className="desc">{compactDescription(profile)}</p>

        <div className="mini-stat-grid">
          <ArchiveMetric label="文件" value={profile.document_count} />
          <ArchiveMetric label="片段" value={profile.chunk_count} />
          <ArchiveMetric label="画像" value={profile.has_analysis ? '完成' : '待'} />
          <ArchiveMetric label="模拟" value={simulationReady ? '可用' : '待'} />
        </div>

        <div className="profile-card-footer compact-footer">
          <span>更新 {formatDate(profile.updated_at || profile.created_at)}</span>
          <span>创建 {formatDate(profile.created_at)}</span>
        </div>
      </article>
    </Link>
  )
}

function ArchiveRowList({ profiles }: { profiles: Profile[] }) {
  return (
    <div className="archive-row-list">
      <div className="archive-row archive-row-head">
        <span>人物</span>
        <span>资料</span>
        <span>画像</span>
        <span>模拟</span>
        <span>最近更新</span>
        <span />
      </div>
      {profiles.map(profile => {
        const simulationReady = isSimulationReady(profile)
        return (
          <Link to={`/profiles/${profile.id}`} className="archive-row" key={profile.id}>
            <span className="archive-row-person">
              <strong>{profile.name}</strong>
              <em>{relationshipLabel(profile.relationship_type)}</em>
            </span>
            <span>{profile.document_count} 文件 / {profile.chunk_count} 片段</span>
            <span className={profile.has_analysis ? 'badge badge-success' : 'badge badge-warning'}>
              {profile.has_analysis ? '已完成' : '待分析'}
            </span>
            <span className={simulationReady ? 'badge badge-success' : 'badge badge-muted'}>
              {simulationReady ? '可用' : '未准备'}
            </span>
            <span>{formatDate(profile.updated_at || profile.created_at)}</span>
            <span className="archive-row-open">打开</span>
          </Link>
        )
      })}
    </div>
  )
}

function ArchiveStatusMatrix({ profiles }: { profiles: Profile[] }) {
  return (
    <div className="archive-status-matrix">
      {profiles.map(profile => {
        const dataReady = profile.document_count > 0 || profile.chunk_count > 0
        const simulationReady = isSimulationReady(profile)
        return (
          <Link to={`/profiles/${profile.id}`} className="status-matrix-row" key={profile.id}>
            <div>
              <strong>{profile.name}</strong>
              <span>{relationshipLabel(profile.relationship_type)}</span>
            </div>
            <MatrixDot label="资料" status={dataReady ? 'done' : 'pending'} />
            <MatrixDot label="画像" status={profile.has_analysis ? 'done' : dataReady ? 'warning' : 'pending'} />
            <MatrixDot label="模拟" status={simulationReady ? 'done' : profile.has_analysis ? 'warning' : 'pending'} />
            <MatrixDot label="导出" status={profile.has_analysis ? 'done' : 'pending'} />
            <span className="archive-row-open">打开</span>
          </Link>
        )
      })}
    </div>
  )
}

function MatrixDot({ label, status }: { label: string; status: 'done' | 'pending' | 'warning' }) {
  return (
    <span className="matrix-dot-cell">
      <i className={`matrix-dot ${status}`} />
      {label}
    </span>
  )
}

function ArchiveMetric({ label, value }: { label: string; value: string | number }) {
  return (
    <div>
      <span>{label}</span>
      <strong>{value}</strong>
    </div>
  )
}

function isSimulationReady(profile: Profile): boolean {
  return Boolean(profile.has_analysis && profile.chunk_count > 0)
}

function compactDescription(profile: Profile): string {
  return profile.description?.trim() || '暂无描述。上传资料后可生成画像与模拟。'
}

function relationshipLabel(t: string): string {
  const map: Record<string, string> = {
    friend: '朋友', family: '亲人', colleague: '同事',
    lover: '伴侣/白月光', public_figure: '公众人物',
    author: '作者/IP', other: '其他',
  }
  return map[t] || t
}

function formatDate(date: string): string {
  return new Date(date).toLocaleDateString('zh-CN')
}
