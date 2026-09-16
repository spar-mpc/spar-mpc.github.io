import Icon from './Icon';
import type { IconName } from './Icon';

export default function ResourceLink({ label, href, icon }: { label: string; href: string | null; icon: IconName }) {
  const content = <><Icon name={icon} /><span>{label}</span></>;

  if (!href) {
    return <span className="resource-tag" role="link" aria-disabled="true" title={`${label} link unavailable`}>{content}</span>;
  }

  return (
    <a
      href={href}
      {...(href.startsWith('https://') ? { target: '_blank', rel: 'noopener noreferrer' } : {})}
    >
      {content}
    </a>
  );
}
