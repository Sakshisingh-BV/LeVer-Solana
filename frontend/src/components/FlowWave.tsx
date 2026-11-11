import { useAmbientScene } from '../hooks/useAmbientScene';

/** The decorative scene runs independently from React's render cycle. */
export function FlowWave({ enabled }: { enabled: boolean }) {
  const ref = useAmbientScene(enabled, 'lever:flow-wave', false, '.hero');
  return <div className="flow-background" aria-hidden="true">{enabled && <iframe ref={ref} src="/flow-wave/index.html?embed" title="Decorative Flow Wave animation" tabIndex={-1}/>}</div>;
}
