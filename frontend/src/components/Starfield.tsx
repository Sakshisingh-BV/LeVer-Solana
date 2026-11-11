import { useAmbientScene } from '../hooks/useAmbientScene';

/** The supplied, standalone Three.js scene stays outside React's render cycle. */
export function Starfield({ enabled, paused }: { enabled: boolean; paused: boolean }) {
  const ref = useAmbientScene(enabled, 'lever:starfield', paused);
  return <div className="ambient-background" aria-hidden="true">{enabled && <iframe ref={ref} src="/starfield/index.html?embed" title="Decorative starfield" tabIndex={-1} />}</div>;
}
