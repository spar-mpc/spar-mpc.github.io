import { useEffect, useRef, useState } from 'react';
import { citation } from '../data/site';
import Icon from './Icon';

export default function Citation() {
  const [status, setStatus] = useState<'idle' | 'copied' | 'failed'>('idle');
  const timer = useRef<ReturnType<typeof setTimeout> | null>(null);
  useEffect(() => () => { if (timer.current) clearTimeout(timer.current); }, []);
  async function copy() {
    try {
      await navigator.clipboard.writeText(citation);
      setStatus('copied');
    } catch {
      setStatus('failed');
    }
    if (timer.current) clearTimeout(timer.current);
    timer.current = setTimeout(() => setStatus('idle'), 3500);
  }
  return <section className="citation-section section" id="citation" aria-labelledby="citation-title">
    <div className="citation-heading"><h2 id="citation-title">BibTeX</h2><button className="copy-button" type="button" onClick={copy}><Icon name={status === 'copied' ? 'check' : 'copy'}/>{status === 'copied' ? 'Copied' : 'Copy BibTeX'}</button></div>
    <div className="citation-details"><pre className="citation-code"><code>{citation}</code></pre></div>
    <span className="copy-status" role="status">{status === 'failed' ? 'Clipboard unavailable. Select and copy the citation manually.' : status === 'copied' ? 'BibTeX copied to clipboard.' : ''}</span>
  </section>;
}
