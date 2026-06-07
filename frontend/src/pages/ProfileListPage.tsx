import { useState, useEffect } from 'react'
import { Link } from 'react-router-dom'
import { listProfiles, createProfile, type Profile } from '../api/client'

export default function ProfileListPage() {
  const [profiles, setProfiles] = useState<Profile[]>([])
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState('')
  const [showModal, setShowModal] = useState(false)
  const [form, setForm] = useState({ name: '', description: '', relationship_type: 'other' })
  const [submitting, setSubmitting] = useState(false)

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

  return (
    <div className="fade-in">
      <div className="page-header">
        <div>
          <h1>人物档案</h1>
          <p>管理资料、画像状态和模拟实验入口。</p>
        </div>
        <button className="btn-primary" onClick={() => setShowModal(true)}>新建人物档案</button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <div className="empty-state"><div className="spinner" style={{ margin: '0 auto' }} /></div>
      ) : profiles.length === 0 ? (
        <div className="card empty-state">
          <h3>还没有人物档案</h3>
          <p>创建第一个人物档案后，上传资料、生成画像，再进入模拟对话或导出报告。</p>
          <button className="btn-primary" style={{ marginTop: '1rem' }} onClick={() => setShowModal(true)}>
            创建第一个档案
          </button>
        </div>
      ) : (
        <div className="profile-grid">
          {profiles.map((p) => (
            <Link to={`/profiles/${p.id}`} key={p.id} style={{ color: 'inherit', textDecoration: 'none' }}>
              <article className="card profile-card" style={{ cursor: 'pointer' }}>
                <h3>{p.name}</h3>
                <div className="meta">
                  <span className="badge">{relationshipLabel(p.relationship_type)}</span>
                  <span className={p.has_analysis ? 'badge badge-success' : 'badge badge-muted'}>
                    {p.has_analysis ? '已分析' : '待分析'}
                  </span>
                </div>
                <p className="desc">{p.description || '暂无描述。可在详情页上传资料并生成证据化画像。'}</p>
                <div className="quality-grid" style={{ gridTemplateColumns: 'repeat(2, minmax(0, 1fr))', gap: '0.5rem' }}>
                  <div className="metric-card">
                    <div className="metric-label">Files</div>
                    <div className="metric-value">{p.document_count}</div>
                  </div>
                  <div className="metric-card">
                    <div className="metric-label">Chunks</div>
                    <div className="metric-value">{p.chunk_count}</div>
                  </div>
                </div>
                <div className="profile-card-footer">
                  <span>创建 {formatDate(p.created_at)}</span>
                  <span>更新 {formatDate(p.updated_at || p.created_at)}</span>
                </div>
              </article>
            </Link>
          ))}
        </div>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowModal(false) }}>
          <div className="modal-content">
            <div className="modal-header">
              <div>
                <h2>新建人物档案</h2>
                <p style={{ color: 'var(--muted)', fontSize: '0.84rem' }}>先建立档案，再上传授权资料进行画像分析。</p>
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
                {submitting ? <><span className="spinner" /> 创建中</> : '创建'}
              </button>
            </div>
          </div>
        </div>
      )}
    </div>
  )
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
