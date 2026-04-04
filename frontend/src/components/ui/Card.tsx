import React from 'react';

export interface CardProps {
  children: React.ReactNode;
  className?: string;
  padding?: 'none' | 'sm' | 'md' | 'lg';
  hover?: boolean;
  onClick?: () => void;
}

export const Card: React.FC<CardProps> = ({
  children,
  className = '',
  padding = 'md',
  hover = false,
  onClick,
}) => {
  const paddingStyles = {
    none: '',
    sm: 'p-3',
    md: 'p-4',
    lg: 'p-6',
  };

  return (
    <div
      className={`rounded-ds ${paddingStyles[padding]} ${hover ? 'cursor-pointer' : ''} ${className}`}
      style={{
        backgroundColor: 'var(--surface)',
        border: '1px solid var(--border)',
      }}
      onClick={onClick}
      onMouseEnter={hover ? (e) => { e.currentTarget.style.borderColor = 'var(--text-muted)'; } : undefined}
      onMouseLeave={hover ? (e) => { e.currentTarget.style.borderColor = 'var(--border)'; } : undefined}
    >
      {children}
    </div>
  );
};

export interface CardHeaderProps {
  children: React.ReactNode;
  className?: string;
}

export const CardHeader: React.FC<CardHeaderProps> = ({ children, className = '' }) => {
  return (
    <div className={`pb-3 mb-4 ${className}`} style={{ borderBottom: '1px solid var(--border)' }}>
      {children}
    </div>
  );
};

export interface CardTitleProps {
  children: React.ReactNode;
  className?: string;
}

export const CardTitle: React.FC<CardTitleProps> = ({ children, className = '' }) => {
  return (
    <h3 className={`font-semibold ${className}`} style={{ color: 'var(--text-primary)', fontSize: '20px', fontWeight: 700, lineHeight: 1.3 }}>
      {children}
    </h3>
  );
};

export interface CardContentProps {
  children: React.ReactNode;
  className?: string;
}

export const CardContent: React.FC<CardContentProps> = ({ children, className = '' }) => {
  return <div className={className}>{children}</div>;
};
