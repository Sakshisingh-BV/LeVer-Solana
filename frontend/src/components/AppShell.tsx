import { useEffect, useRef, useState } from 'react';
import { Link, NavLink, useLocation } from 'react-router-dom';
import { ArrowUpRight, Github, Menu, Sparkles, X } from 'lucide-react';
import type { ReactNode } from 'react';
import { FlowWave } from './FlowWave';

export function LeVerLogo() {
  return <span className="lever-logo"><svg viewBox="0 0 32 32" fill="none" aria-hidden="true"><path d="M5 5v22h22" stroke="currentColor" strokeWidth="4"/><path d="m13 6 7 14L28 6" stroke="currentColor" strokeWidth="4"/></svg><span>LeVer<span className="logo-period">.</span></span></span>;
}
export function AppShell({ children, ambient, onToggleAmbient }: { children: ReactNode; ambient: boolean; onToggleAmbient: () => void }) {
  const location = useLocation();
  const [menuOpen, setMenuOpen] = useState(false);
  const menuButton = useRef<HTMLButtonElement>(null);
  const home = location.pathname === '/';
  useEffect(() => {
    setMenuOpen(false);
    if (location.hash) {
      const frame = requestAnimationFrame(() => document.getElementById(location.hash.slice(1))?.scrollIntoView({ behavior: 'smooth' }));
      return () => cancelAnimationFrame(frame);
    }
    window.scrollTo({ top: 0, behavior: 'instant' });
  }, [location.pathname, location.hash]);
  useEffect(() => {
    const escape = (event: KeyboardEvent) => { if (event.key === 'Escape' && menuOpen) { setMenuOpen(false); menuButton.current?.focus(); } };
    window.addEventListener('keydown', escape); return () => window.removeEventListener('keydown', escape);
  }, [menuOpen]);
  return <div className={`site-shell ${home ? 'is-landing' : 'is-workspace'}`}>
    {home && <FlowWave enabled={ambient} />}
    <a className="skip-link" href="#main-content">Skip to content</a>
    <header className="site-header"><div className="nav-container">
      <Link to="/" aria-label="LeVer home"><LeVerLogo /></Link>
      <nav className={`site-nav ${menuOpen ? 'is-open' : ''}`} aria-label="Main navigation" id="site-navigation">
        <NavLink to="/" end>Home</NavLink><Link to="/#about">About</Link><Link to="/#how-it-works">How It Works</Link><Link to="/#modes">Modes</Link><a href="https://github.com/gl-bowei/LeVer" target="_blank" rel="noreferrer"><Github size={15} />GitHub<ArrowUpRight size={12} /></a>
      </nav>
      <div className="site-nav-actions"><button className="motion-button" aria-label={ambient ? 'Pause background animation' : 'Enable background animation'} aria-pressed={ambient} title={ambient ? 'Pause background animation' : 'Enable background animation'} onClick={onToggleAmbient}><Sparkles size={17}/></button><Link to="/build" className="nav-cta">Open builder<ArrowUpRight size={15}/></Link><button ref={menuButton} className="menu-toggle" aria-label={menuOpen ? 'Close menu' : 'Open menu'} aria-expanded={menuOpen} aria-controls="site-navigation" onClick={() => setMenuOpen(!menuOpen)}>{menuOpen ? <X size={22}/> : <Menu size={22}/>}</button></div>
    </div></header>
    {!home && <div className="workspace-subnav"><span>DEVELOPER WORKSPACE</span><nav aria-label="Builder navigation"><NavLink to="/build">Create code</NavLink><NavLink to="/runs">Your builds</NavLink><NavLink to="/properties">Properties</NavLink><NavLink to="/docs">Documentation</NavLink></nav></div>}
    <main id="main-content" className={home ? 'landing-content' : 'workspace-content'}>{children}</main>
    <footer className="site-footer"><div><Link to="/" aria-label="LeVer home"><LeVerLogo/></Link><p>From intent to on-chain.</p></div><span>One platform. Two ecosystems. More possibilities.</span><div className="footer-links"><Link to="/docs">Documentation</Link><a href="https://github.com/gl-bowei/LeVer" target="_blank" rel="noreferrer">GitHub<ArrowUpRight size={12}/></a></div></footer>
  </div>;
}
