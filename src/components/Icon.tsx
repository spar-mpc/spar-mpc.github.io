import type { CSSProperties } from 'react';

export type IconName = 'satellite' | 'paper' | 'code' | 'arrow' | 'copy' | 'check' | 'drone' | 'car' | 'download';
export default function Icon({ name, size = 18, style, className }: { name: IconName; size?: number; style?: CSSProperties; className?: string }) {
  return <svg width={size} height={size} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true" style={style} className={className}>
    {name === 'satellite' && <g transform="rotate(-35 12 12)"><rect x="9" y="7" width="6" height="10" rx="1"/><path d="M1 9h6v6H1zM17 9h6v6h-6zM7 12h2m6 0h2M12 7V3m-2-2 2 2 2-2"/></g>}
    {name === 'paper' && <><path d="M6 3h8l4 4v14H6zM14 3v5h4M9 12h6M9 16h6"/></>}
    {name === 'code' && <><path d="m8 7-5 5 5 5m8-10 5 5-5 5m-3-13-2 16"/></>}
    {name === 'arrow' && <path d="M5 12h14m-6-6 6 6-6 6"/>}
    {name === 'copy' && <><rect x="8" y="8" width="12" height="13" rx="2"/><path d="M16 8V3H3v13h5"/></>}
    {name === 'check' && <path d="m5 12 4 4L19 6"/>}
    {name === 'download' && <><path d="M12 3v12m-5-5 5 5 5-5M4 16v5h16v-5"/></>}
    {name === 'drone' && <><rect x="9" y="9" width="6" height="6" rx="2"/><path d="m9 9-3-3m9 3 3-3m-3 9 3 3m-9-3-3 3"/><ellipse cx="5" cy="5" rx="4" ry="2"/><ellipse cx="19" cy="5" rx="4" ry="2"/><ellipse cx="5" cy="19" rx="4" ry="2"/><ellipse cx="19" cy="19" rx="4" ry="2"/></>}
    {name === 'car' && <><path d="m4 11 2-6h12l2 6m-17 0h18v8H3zM5 19v2m14-2v2M7 15h1m8 0h1M10 2h4"/></>}
  </svg>;
}
