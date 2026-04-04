import React from 'react';

export interface ButtonProps extends React.ButtonHTMLAttributes<HTMLButtonElement> {
  variant?: 'primary' | 'secondary' | 'danger' | 'ghost';
  size?: 'sm' | 'md' | 'lg';
  isLoading?: boolean;
  children: React.ReactNode;
}

export const Button: React.FC<ButtonProps> = ({
  variant = 'primary',
  size = 'md',
  isLoading = false,
  children,
  className = '',
  disabled,
  style,
  ...props
}) => {
  const sizeStyles: Record<NonNullable<ButtonProps['size']>, React.CSSProperties> = {
    sm: { padding: '4px 10px', fontSize: '12px' },
    md: { padding: '8px 18px', fontSize: '14px' },
    lg: { padding: '10px 28px', fontSize: '15px', fontWeight: 600 },
  };

  const variantMap: Record<NonNullable<ButtonProps['variant']>, React.CSSProperties> = {
    primary: {
      backgroundColor: 'var(--color-primary)',
      border: '1px solid var(--color-primary)',
      color: '#ffffff',
    },
    secondary: {
      backgroundColor: 'var(--color-surface)',
      border: '1px solid var(--color-border)',
      color: 'var(--color-text)',
    },
    danger: {
      backgroundColor: 'transparent',
      border: '1px solid var(--color-danger)',
      color: 'var(--color-danger)',
    },
    ghost: {
      backgroundColor: 'transparent',
      border: '1px solid transparent',
      color: 'var(--color-text-muted)',
    },
  };

  const hoverStyles: Record<NonNullable<ButtonProps['variant']>, React.CSSProperties> = {
    primary: { backgroundColor: 'var(--color-primary-hover)', borderColor: 'var(--color-primary-hover)' },
    secondary: { backgroundColor: 'var(--color-surface-hover)' },
    danger: { backgroundColor: 'rgba(248,113,113,0.1)' },
    ghost: { backgroundColor: 'var(--color-surface-hover)', color: 'var(--color-text)' },
  };

  return (
    <button
      className={`inline-flex items-center justify-center gap-2 font-medium transition-all disabled:opacity-50 disabled:cursor-not-allowed ${className}`}
      style={{
        borderRadius: 'var(--radius)',
        lineHeight: 1,
        ...sizeStyles[size],
        ...variantMap[variant],
        ...style,
      }}
      onMouseEnter={(e) => {
        const hover = hoverStyles[variant];
        Object.assign(e.currentTarget.style, hover);
      }}
      onMouseLeave={(e) => {
        Object.assign(e.currentTarget.style, {
          backgroundColor: variantMap[variant].backgroundColor,
          border: variantMap[variant].border,
          color: variantMap[variant].color,
        });
      }}
      disabled={disabled || isLoading}
      {...props}
    >
      {isLoading && (
        <svg
          className="animate-spin -ml-1 mr-2 h-4 w-4"
          xmlns="http://www.w3.org/2000/svg"
          fill="none"
          viewBox="0 0 24 24"
        >
          <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4" />
          <path className="opacity-75" fill="currentColor"
            d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z" />
        </svg>
      )}
      {children}
    </button>
  );
};
