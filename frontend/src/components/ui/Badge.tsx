import React from 'react';

export interface BadgeProps {
  children: React.ReactNode;
  variant?: 'success' | 'warning' | 'danger' | 'primary' | 'muted' | 'purple';
  className?: string;
}

export const Badge: React.FC<BadgeProps> = ({
  children,
  variant = 'muted',
  className = '',
}) => {
  const variantStyles: Record<string, React.CSSProperties> = {
    success: {
      background: 'rgba(52, 211, 153, 0.15)',
      color: 'var(--color-success)',
    },
    warning: {
      background: 'rgba(251, 191, 36, 0.15)',
      color: 'var(--color-warning)',
    },
    danger: {
      background: 'rgba(248, 113, 113, 0.15)',
      color: 'var(--color-danger)',
    },
    primary: {
      background: 'rgba(74, 124, 255, 0.15)',
      color: 'var(--color-primary)',
    },
    muted: {
      background: 'rgba(139, 143, 163, 0.15)',
      color: 'var(--color-text-muted)',
    },
    purple: {
      background: 'rgba(167, 139, 250, 0.15)',
      color: '#a78bfa',
    },
  };

  return (
    <span
      className={`inline-block ${className}`}
      style={{
        fontSize: '11px',
        padding: '3px 10px',
        borderRadius: '999px',
        fontWeight: 600,
        ...variantStyles[variant],
      }}
    >
      {children}
    </span>
  );
};
