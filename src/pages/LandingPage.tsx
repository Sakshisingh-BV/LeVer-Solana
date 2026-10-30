import { Link } from 'react-router-dom';
import { ArrowDown, ArrowRight, ArrowUpRight, Braces, Check, Code2, FileCheck2, FileText, GitBranch, MessageSquareText, ShieldCheck, Sparkles } from 'lucide-react';
import NewRunPage from './NewRunPage';
import { TargetIcon } from '../components/ui';
import type { RunInput } from '../types/run';

const features = [
  { icon: MessageSquareText, number: '01', title: 'Natural language. Real intent.', copy: 'Turn plain-English requirements into structured technical specifications. Start with what you want to build.' },
  { icon: Braces, number: '02', title: 'Your idea, in source code.', copy: 'Generate blockchain-specific source code for Ethereum or Solana, in one connected workspace.' },
  { icon: ShieldCheck, number: '03', title: 'More than generation.', copy: 'Analyze potential vulnerabilities, inspect verification evidence, and review repairs alongside your code.' },
];
const steps = [
  { icon: MessageSquareText, title: 'Requirement Input', copy: 'Describe the behavior and rules in plain English.' },
  { icon: FileText, title: 'Specification Generation', copy: 'Translate your intent into a structured specification.' },
  { icon: Code2, title: 'Code Generation', copy: 'Create source code for your chosen ecosystem.' },
  { icon: ShieldCheck, title: 'Verification & Repair', copy: 'Analyze the code and refine it where applicable.' },
  { icon: FileCheck2, title: 'Final Output', copy: 'Review your source code and the available evidence.' },
];
export default function LandingPage(props: { onRun: (input: RunInput) => void; notify: (message: string) => void }) {
  return <>
    <section className="hero" id="home"><div className="hero-inner"><div className="hero-copy">
      <Link to="/#about" className="hero-label"><span className="live-dot"/>AI-POWERED BLOCKCHAIN DEVELOPMENT<ArrowUpRight size={12}/></Link>
      <h1>From Natural<br/>Language to<br/><span>Blockchain Code.</span></h1>
      <p>Transform your ideas into blockchain-ready code with AI-powered generation, verification and vulnerability analysis.</p>
      <div className="hero-actions"><Link to="/#build" className="button primary hero-primary">Get Started<ArrowRight size={17}/></Link><Link to="/#about" className="button hero-secondary">Explore LeVer<ArrowUpRight size={17}/></Link></div>
      <div className="hero-ecosystems"><span>BUILT FOR</span><span><TargetIcon target="solidity"/>Ethereum</span><span className="ecosystem-divider"/><span><TargetIcon target="solana"/>Solana</span></div>
    </div>
    <div className="hero-visual" aria-label="Illustration of a requirement becoming source code">
      <div className="intent-card"><div className="visual-icon"><Sparkles size={18}/></div><div><span>YOUR IDEA</span><p>“A token vault. Deposits for everyone.<br/>Withdrawals for the owner.”</p></div></div>
      <div className="visual-connector"><span/><GitBranch size={17}/><span/></div>
      <div className="hero-code-card"><div className="hero-code-title"><div className="window-dots"><i/><i/><i/></div><span>TokenVault.sol</span><span className="code-language">SOLIDITY</span></div>
        <div className="hero-code"><div><i>01</i><code><span className="c-comment">// Your idea, expressed in code.</span></code></div><div><i>02</i><code><span className="c-purple">pragma</span> solidity ^0.8.24;</code></div><div><i>03</i><code>&nbsp;</code></div><div><i>04</i><code><span className="c-purple">contract</span> <span className="c-mint">TokenVault</span> {'{'}</code></div><div><i>05</i><code>  <span className="c-purple">address public</span> owner;</code></div><div><i>06</i><code>&nbsp;</code></div><div><i>07</i><code>  <span className="c-purple">modifier</span> <span className="c-blue">onlyOwner</span>() {'{'}</code></div><div><i>08</i><code>    <span className="c-blue">require</span>(msg.sender == owner);</code></div><div><i>09</i><code>    _;</code></div><div><i>10</i><code>  {'}'}</code></div><div><i>11</i><code>{'}'}</code></div></div>
        <div className="hero-code-footer"><span><span/>ILLUSTRATIVE SOURCE</span><Link to="/preview/solidity">Explore output<ArrowUpRight size={12}/></Link></div>
      </div><div className="visual-caption"><span className="caption-line"/>Intent. Code. Evidence.</div>
    </div></div>
    <div className="hero-bottom"><span><ShieldCheck size={14}/>Built around generation, verification & repair</span><Link to="/#about">DISCOVER WHAT'S POSSIBLE<ArrowDown size={14}/></Link><span className="hero-index">01 — THE POSSIBILITIES</span></div></section>
    <div className="landing-sections">
      <section className="about-section section-container" id="about"><div className="section-heading"><span className="section-kicker"><span/>MEET LEVER</span><div className="section-heading-row"><h2>What is LeVer?</h2><span className="small-section-note">LESS FRICTION.<br/>MORE POSSIBILITY.</span></div><p>LeVer is an AI-driven smart contract generation and vulnerability repair framework that translates natural language requirements into smart contract code. It combines language-model-based reasoning with formal methods to help generate, analyze and improve smart contracts.</p></div><div className="feature-grid">{features.map(feature => <article className="feature-card" key={feature.number}><div className="feature-card-top"><span className="feature-icon"><feature.icon size={22}/></span><span>{feature.number}</span></div><h3>{feature.title}</h3><p>{feature.copy}</p></article>)}</div></section>
      <section className="how-section section-container" id="how-it-works"><div className="section-heading"><span className="section-kicker"><span/>A CONNECTED WORKFLOW</span><h2>One idea. A clear path forward.</h2><p>From the first sentence to the final source file, every step has a purpose.</p></div><ol className="landing-workflow">{steps.map((step, index) => <li key={step.title}><div className="workflow-node"><step.icon size={22}/><span>{String(index + 1).padStart(2, '0')}</span></div><h3>{step.title}</h3><p>{step.copy}</p></li>)}</ol><div className="workflow-footnote"><Check size={14}/>Execution follows your selected mode and the capabilities of your connected pipeline.</div></section>
      <section className="builder-section section-container" id="build"><NewRunPage {...props} embedded/></section>
      <section className="closing-section section-container"><span className="section-kicker"><span/>BUILT FOR THE NEXT IDEA</span><h2>Make your next move<br/><span>an on-chain one.</span></h2><Link to="/#build" className="button primary">Start building<ArrowRight size={17}/></Link><a className="closing-source" href="https://github.com/gl-bowei/LeVer" target="_blank" rel="noreferrer">Explore the open-source framework<ArrowUpRight size={14}/></a></section>
    </div>
  </>;
}
