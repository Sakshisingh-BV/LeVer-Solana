import { useState } from 'react';
import { ArrowUpRight, BookOpen, ShieldCheck } from 'lucide-react';
import { Dialog } from '../components/ui';
import { propertyExamples } from '../data/examples';

export default function PropertiesPage() {
  const [target, setTarget] = useState('all');
  const [selected, setSelected] = useState<typeof propertyExamples[number] | null>(null);
  const filtered = propertyExamples.filter(property => target === 'all' || property.target === 'both' || property.target === target);
  return <>
    <div className="page-heading"><div><div className="eyebrow"><span className="eyebrow-line" />PROPERTY LIBRARY</div><h1>Make the rules <em>explicit.</em></h1><p>Reference examples for the properties a contract should preserve.</p></div><span className="quiet-badge"><BookOpen size={14} />Reference only</span></div>
    <div className="filter-tabs library-tabs" role="group" aria-label="Property target">{['all', 'solidity', 'solana'].map(value => <button key={value} className={target === value ? 'active' : ''} aria-pressed={target === value} onClick={() => setTarget(value)}>{value === 'all' ? 'All properties' : value === 'solidity' ? 'Solidity' : 'Solana'}</button>)}</div>
    <div className="property-grid">{filtered.map(property => <button className="property-card" key={property.id} onClick={() => setSelected(property)}><div className="property-topline"><ShieldCheck size={19} /><span>{property.target === 'both' ? 'CROSS-CHAIN' : property.target.toUpperCase()}</span><ArrowUpRight size={16} /></div><span className="property-category">{property.category}</span><h2>{property.name}</h2><p>{property.description}</p><span className="property-read">Read property<ArrowUpRight size={13} /></span></button>)}</div>
    <p className="data-caption">Illustrative property descriptions. This screen does not select or prove backend properties.</p>
    {selected && <Dialog title={selected.name} onClose={() => setSelected(null)}><span className="quiet-badge">{selected.category}</span><p className="property-detail">{selected.detail}</p><div className="dialog-note">The actual verifier needs a precise specification, implementation context and matching assumptions.</div></Dialog>}
  </>;
}
