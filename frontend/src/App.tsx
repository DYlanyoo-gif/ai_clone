import { Component } from 'react'
import { Routes, Route, Link } from 'react-router-dom'
import Layout from './components/Layout'
import HomePage from './pages/HomePage'
import ProfileListPage from './pages/ProfileListPage'
import ProfileDetailPage from './pages/ProfileDetailPage'
import ChatPage from './pages/ChatPage'

class ErrorBoundary extends Component<{ children: React.ReactNode }, { hasError: boolean; error: Error | null }> {
  constructor(props: { children: React.ReactNode }) {
    super(props)
    this.state = { hasError: false, error: null }
  }

  static getDerivedStateFromError(error: Error) {
    return { hasError: true, error }
  }

  render() {
    if (this.state.hasError) {
      return (
        <Layout>
          <div>
            <div className="alert alert-error" style={{ marginBottom: '1rem' }}>
              <h2>页面发生错误</h2>
              <p style={{ fontSize: '0.85rem', marginTop: '0.5rem', wordBreak: 'break-all' }}>
                {this.state.error?.message || '未知错误'}
              </p>
            </div>
            <div style={{ display: 'flex', gap: '0.5rem', flexWrap: 'wrap' }}>
              <button onClick={() => window.location.reload()} className="btn-primary">
                刷新页面
              </button>
              <Link to="/" className="btn-primary" style={{ background: 'var(--c-text-muted)', borderColor: 'var(--c-text-muted)' }}>
                返回首页
              </Link>
            </div>
          </div>
        </Layout>
      )
    }
    return this.props.children
  }
}

export default function App() {
  return (
    <Layout>
      <ErrorBoundary>
        <Routes>
          <Route path="/" element={<HomePage />} />
          <Route path="/profiles" element={<ProfileListPage />} />
          <Route path="/profiles/:id" element={<ProfileDetailPage />} />
          <Route path="/profiles/:id/chat" element={<ChatPage />} />
        </Routes>
      </ErrorBoundary>
    </Layout>
  )
}
