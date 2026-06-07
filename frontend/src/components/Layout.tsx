import { Link, useLocation } from 'react-router-dom'

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + '/')

  return (
    <div className="app-shell">
      <nav className="app-nav">
        <div className="app-nav-inner">
          <Link to="/" className="brand-lockup" aria-label="Persona Archive 首页">
            <span className="brand-mark">EA</span>
            <span>
              <span className="brand-name">Echo Profile</span>
              <span className="brand-subtitle">证据化人物画像系统</span>
            </span>
          </Link>
          <div className="nav-links">
            <Link to="/" className={location.pathname === '/' ? 'active' : ''}>工作台</Link>
            <Link to="/profiles" className={isActive('/profiles') ? 'active' : ''}>人物档案</Link>
          </div>
        </div>
      </nav>
      <main>{children}</main>
    </div>
  )
}
