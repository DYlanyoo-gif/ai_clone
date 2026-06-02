import { Link, useLocation } from 'react-router-dom'

export default function Layout({ children }: { children: React.ReactNode }) {
  const location = useLocation()
  const isActive = (path: string) => location.pathname === path || location.pathname.startsWith(path + '/')

  return (
    <div className="app-layout">
      <nav className="app-nav">
        <Link to="/" className="logo">AI Clone</Link>
        <div className="nav-links">
          <Link to="/" className={location.pathname === '/' ? 'active' : ''}>首页</Link>
          <Link to="/profiles" className={isActive('/profiles') ? 'active' : ''}>人物档案</Link>
        </div>
      </nav>
      <main>{children}</main>
    </div>
  )
}
