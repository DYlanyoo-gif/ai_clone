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
    <div>
      <div className="page-header">
        <h1>人物档案</h1>
        <button className="btn-primary" onClick={() => setShowModal(true)}>+ 新建人物</button>
      </div>

      {error && <div className="alert alert-error">{error}</div>}

      {loading ? (
        <div className="empty-state"><div className="spinner" style={{ margin: '0 auto' }} /></div>
      ) : profiles.length === 0 ? (
        <div className="empty-state">
          <h3>还没有人物档案</h3>
          <p>点击"新建人物"按钮创建第一个档案</p>
        </div>
      ) : (
        <div className="profile-grid">
          {profiles.map((p) => (
            <Link to={`/profiles/${p.id}`} key={p.id} style={{ color: 'inherit', textDecoration: 'none' }}>
              <div className="card profile-card" style={{ cursor: 'pointer', transition: 'box-shadow 0.2s' }}
                onMouseEnter={e => (e.currentTarget.style.boxShadow = 'var(--shadow-lg)')}
                onMouseLeave={e => (e.currentTarget.style.boxShadow = 'var(--shadow)')}
              >
                <h3>{p.name}</h3>
                <div className="meta">
                  <span className="badge">{relationshipLabel(p.relationship_type)}</span>
                  {p.has_analysis && <span className="badge" style={{ background: '#dcfce7', color: '#16a34a' }}>已分析</span>}
                  <span className="badge" style={{ background: '#f1f5f9', color: 'var(--c-text-muted)' }}>
                    {p.document_count} 个文件 · {p.chunk_count} 片段
                  </span>
                </div>
                {p.description && <p className="desc">{p.description}</p>}
                <div style={{ marginTop: '0.5rem', fontSize: '0.8rem', color: 'var(--c-text-muted)' }}>
                  创建于 {new Date(p.created_at).toLocaleDateString('zh-CN')}
                </div>
              </div>
            </Link>
          ))}
        </div>
      )}

      {showModal && (
        <div className="modal-overlay" onClick={e => { if (e.target === e.currentTarget) setShowModal(false) }}>
          <div className="modal-content">
            <h2>新建人物档案</h2>
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
              <button onClick={() => setShowModal(false)}>取消</button>
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
