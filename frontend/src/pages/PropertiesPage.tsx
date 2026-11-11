import { useEffect, useState } from 'react';
import { ArrowUpRight, BookOpen, CircleAlert, ShieldCheck } from 'lucide-react';
import { Dialog } from '../components/ui';
import { propertyExamples } from '../data/examples';
import { fetchProperties } from '../lib/generation';
import type { PropertyEntry } from '../types/run';

type Catalogue = { status: 'loading' | 'ready' | 'offline'; properties: PropertyEntry[]; error?: string };

/** Static reference examples, shaped like catalogue entries, used only when the backend is unreachable. */
const fallback: PropertyEntry[] = propertyExamples.map(item => ({ id: item.id, name: item.name, category: item.category, description: item.description, target: item.target, invariant_template: item.detail }));

export default function PropertiesPage() {
  const [target, setTarget] = useState('all');
  const [selected, setSelected] = useState<PropertyEntry | null>(null);
  const [catalogue, setCatalogue] = useState<Catalogue>({ status: 'loading', properties: [] });
  useEffect(() => {
    const controller = new AbortController();
    fetchProperties('all', controller.signal)
      .then(properties => setCatalogue({ status: 'ready', properties }))
      .catch((error: unknown) => { if (!controller.signal.aborted) setCatalogue({ status: 'offline', properties: [], error: error instanceof Error ? error.message : 'Backend unreachable.' }); });
    return () => controller.abort();
  }, []);
  const live = catalogue.status === 'ready';
  const source = live ? catalogue.properties : fallback;
  const filtered = source.filter(property => target === 'all' || property.target === 'both' || property.target === target);
  const counts = { solidity: source.filter(p => p.target === 'solidity').length, solana: source.filter(p => p.target === 'solana').length };
  return <>
    <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" />PROPERTY LIBRARY</div><h1>Make the rules <em>explicit.</em></h1><p>{live ? `${source.length} safety properties served by the backend catalogue (${counts.solidity} Solidity · ${counts.solana} Solana).` : 'The properties the verification pipeline can select for a contract.'}</p></div><span className="quiet-badge"><BookOpen size={14} />{catalogue.status === 'loading' ? 'Loading catalogue…' : live ? 'Live backend catalogue' : 'Reference only'}</span></div>
    {catalogue.status === 'offline' && <div className="inline-notice" role="status"><CircleAlert size={14} /> Backend catalogue unavailable ({catalogue.error}). Showing illustrative examples instead.</div>}
    <div className="filter-tabs library-tabs" role="group" aria-label="Property target">{['all', 'solidity', 'solana'].map(value => <button key={value} className={target === value ? 'active' : ''} aria-pressed={target === value} onClick={() => setTarget(value)}>{value === 'all' ? 'All properties' : value === 'solidity' ? 'Solidity' : 'Solana'}</button>)}</div>
    <div className="property-grid">{filtered.map(property => <button className="property-card" key={`${property.target}-${property.id}`} onClick={() => setSelected(property)}><div className="property-topline"><ShieldCheck size={19} /><span>{property.target === 'both' ? 'CROSS-CHAIN' : property.target.toUpperCase()}{property.severity ? ` · ${String(property.severity).toUpperCase()}` : ''}</span><ArrowUpRight size={16} /></div><span className="property-category">{property.level ? `${property.level.split(':')[0]} · ` : ''}{property.category}</span><h2>{property.name}</h2><p>{property.description}</p><span className="property-read"><code className="mode-code">{property.id}</code>Read property<ArrowUpRight size={13} /></span></button>)}</div>
    {!filtered.length && catalogue.status !== 'loading' && <p className="data-caption">No properties for this ecosystem yet.</p>}
    <p className="data-caption">{live ? 'Properties come from LeVer/property.json (Solidity) and LeVer/properties/solana.json (Solana). The PropertySelector agent picks the relevant ones per run; this page does not pin properties.' : 'Illustrative property descriptions. This screen does not select or prove backend properties.'}</p>
    {selected && <Dialog title={selected.name} onClose={() => setSelected(null)}><span className="quiet-badge">{selected.category}</span>{selected.severity && <span className="quiet-badge">{selected.severity}</span>}<p className="property-detail">{selected.description}</p>{selected.invariant_template && <><h3>Invariant template</h3><pre className="preserve-text">{selected.invariant_template}</pre></>}{selected.remediation && <><h3>Remediation</h3><p className="preserve-text">{selected.remediation}</p></>}{selected.example_attack && <p className="muted">Example attack: {selected.example_attack}</p>}<div className="dialog-note">The actual verifier needs a precise specification, implementation context and matching assumptions.</div></Dialog>}
  </>;
}
