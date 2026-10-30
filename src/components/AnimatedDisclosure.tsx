import { useId, useState } from 'react';
import type { ReactNode } from 'react';
import { ChevronDown } from 'lucide-react';
export function AnimatedDisclosure({ title, children, initialOpen = false }: { title: string; children: ReactNode; initialOpen?: boolean }) {
  const [open, setOpen] = useState(initialOpen);
  const id = useId();
  return <section className={`disclosure ${open ? 'is-open' : ''}`}><button type="button" aria-expanded={open} aria-controls={id} onClick={() => setOpen(!open)}>{title}<ChevronDown size={15} /></button><div id={id} className="disclosure-grid" inert={!open}><div><div className="disclosure-content">{children}</div></div></div></section>;
}
