import React from 'react';

export interface PageHeaderProps {
  title: string;
  subtitle?: string;
  actions?: React.ReactNode;
}

/**
 * PageHeader component following design guide specifications:
 * - H1: 22px, font-weight: 700, line-height: 1.2
 * - Subtitle: 13px, line-height: 1.5, color: muted
 */
export const PageHeader: React.FC<PageHeaderProps> = ({ title, subtitle, actions }) => {
  return (
    <div className="flex items-center justify-between w-full gap-4">
      <div>
        <h1 style={{ fontSize: '22px', fontWeight: 700, lineHeight: 1.2, color: 'var(--color-text)' }}>
          {title}
        </h1>
        {subtitle && (
          <p style={{ fontSize: '13px', lineHeight: 1.5, color: 'var(--color-text-muted)', marginTop: '4px' }}>
            {subtitle}
          </p>
        )}
      </div>
      {actions && <div>{actions}</div>}
    </div>
  );
};
