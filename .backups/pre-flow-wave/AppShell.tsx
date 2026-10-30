import { useEffect, useRef, useState } from 'react';
import { NavLink, useLocation } from 'react-router-dom';
import { ArrowUpRight, BookOpen, ChevronRight, Code2, Command, FileCode2, History, Menu, PanelLeftClose, PanelLeftOpen, Plus, Settings2, Sparkles, WandSparkles, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { Starfield } from './Starfield';
import { usePreference } from '../hooks/usePreference';

export function AppShell({ children, ambient, onToggleAmbient }: { children: ReactNode; ambient: boolean; onToggleAmbient: () => void }) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const [collapsed, setCollapsed] = usePreference('lever.sidebar-collapsed', false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const sidebar = useRef<HTMLElement>(null);
  useEffect(() => { setMenuOpen(false); window.scrollTo({ top: 0, behavior: 'instant' }); }, [location.pathname]);
  useEffect(() => {
    if (!menuOpen) return;
    const focusables = () => [...(sidebar.current?.querySelectorAll<HTMLElement>('a, button') || [])].filter(item => item.offsetParent !== null);
    focusables()[0]?.focus();
    function keyboard(event: KeyboardEvent) {
      if (event.key === 'Escape') { setMenuOpen(false); menuButton.current?.focus(); }
      if (event.key === 'Tab') { const items = focusables(); const first = items[0], last = items.at(-1); if (event.shiftKey && document.activeElement === first) { event.preventDefault(); last?.focus(); } else if (!event.shiftKey && document.activeElement === last) { event.preventDefault(); first?.focus(); } }
    }
    window.addEventListener('keydown', keyboard);
    return () => window.removeEventListener('keydown', keyboard);
  }, [menuOpen]);
  const pageName = location.pathname === '/docs' ? 'Documentation' : location.pathname === '/settings' ? 'Settings' : location.pathname === '/contracts' ? 'Generated contracts' : location.pathname === '/properties' ? 'Property library' : location.pathname === '/runs' ? 'Analysis history' : location.pathname.startsWith('/runs/') || location.pathname.startsWith('/preview') ? 'Contract workspace' : 'New analysis';
  const workspace = location.pathname.startsWith('/runs/') || location.pathname.startsWith('/preview');
  return <div className={`app-shell ${collapsed ? 'sidebar-collapsed' : ''}`}>
    <Starfield enabled={ambient} paused={workspace} />
    <a className="skip-link" href="#main-content">Skip to content</a>
    {menuOpen && <button className="sidebar-backdrop" aria-label="Close navigation" onClick={() => setMenuOpen(false)} />}
    <aside ref={sidebar} className={`sidebar ${menuOpen ? 'is-open' : ''}`} aria-label="Workspace navigation">
      <NavLink to="/" className="brand" aria-label="LeVer home"><span className="brand-symbol"><Code2 size={22} /></span><span className="brand-name">LeVer<span className="brand-period">.</span></span><span className="brand-tag">BETA</span></NavLink>
      <div className="workspace-label"><span className="workspace-avatar">L</span><span>Personal workspace<small>Your ideas, on-chain</small></span><ChevronRight size={13} /></div>
      <NavLink to="/" className="new-experiment" title="New analysis"><Plus size={17} /><span>New analysis</span><Command size={12} /></NavLink>
      <span className="nav-section-label">WORKSPACE</span>
      <nav className="main-nav" aria-label="Main navigation">
        <NavLink to="/" end title="New analysis"><WandSparkles size={18} /><span>New analysis</span></NavLink>
        <NavLink to="/runs" title="Analysis history"><History size={18} /><span>Analysis history</span></NavLink>
        <NavLink to="/contracts" title="Generated contracts"><FileCode2 size={18} /><span>Generated contracts</span></NavLink>
      </nav>
      <div className="sidebar-bottom"><nav className="main-nav secondary-nav" aria-label="Resources"><NavLink to="/docs" title="Documentation"><BookOpen size={18} /><span>Documentation</span><ArrowUpRight size={13} /></NavLink><NavLink to="/settings" title="Settings"><Settings2 size={18} /><span>Settings</span></NavLink></nav>
        <div className="sidebar-note"><span className="tiny-label"><Sparkles size={13} /> FROM IDEA TO CODE</span><p>Build with intention.<br /><em>Verify with confidence.</em></p><NavLink to="/preview/solidity">Explore the workspace<ArrowUpRight size={13} /></NavLink></div>
        <div className="sidebar-footer"><span className="footer-avatar">L</span><span>Local workspace<small>Frontend preview</small></span><button className="icon-button collapse-button" onClick={() => setCollapsed(!collapsed)} aria-label={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} title={collapsed ? 'Expand sidebar' : 'Collapse sidebar'} aria-expanded={!collapsed}>{collapsed ? <PanelLeftOpen size={17} /> : <PanelLeftClose size={17} />}</button></div>
      </div>
    </aside>
    <div className="main-column" inert={menuOpen}>
      <header className="topbar"><div className="breadcrumbs"><button ref={menuButton} className="icon-button mobile-menu" onClick={() => setMenuOpen(!menuOpen)} aria-expanded={menuOpen} aria-label={menuOpen ? 'Close navigation' : 'Open navigation'}>{menuOpen ? <X size={19} /> : <Menu size={19} />}</button><span className="breadcrumb-workspace">Workspace</span><ChevronRight className="breadcrumb-slash" size={13} /><strong>{pageName}</strong></div><div className="topbar-actions"><span className="preview-badge"><span />Frontend preview</span><span className="topbar-divider" /><button className="icon-button ambient-toggle" aria-label={ambient ? 'Turn off starfield' : 'Turn on starfield'} aria-pressed={ambient} title={ambient ? 'Turn off starfield' : 'Turn on starfield'} onClick={onToggleAmbient}><Sparkles size={16} /></button><NavLink className="help-button" to="/docs"><BookOpen size={15} /><span>Docs</span><ArrowUpRight size={12} /></NavLink></div></header>
      <main id="main-content" className="page-content" key={location.pathname}>{children}</main>
      <footer className="page-footer"><span><span className="footer-dot" />Designed for thoughtful builders.</span><span>Solidity & Solana<span className="footer-separator">/</span>LeVer</span></footer>
    </div>
  </div>;
}
