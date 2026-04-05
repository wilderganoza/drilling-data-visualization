import React from 'react';

export interface SpinnerProps {
  size?: number;
  className?: string;
}

export const Spinner: React.FC<SpinnerProps> = ({ size = 32, className = '' }) => {
  return (
    <div
      className={`spinner ${className}`}
      style={{
        width: `${size}px`,
        height: `${size}px`,
        border: '3px solid var(--color-border)',
        borderTopColor: 'var(--color-primary)',
        borderRadius: '50%',
        animation: 'spin 0.8s linear infinite',
      }}
    />
  );
};

export interface InlineLoaderProps {
  message?: string;
  size?: number;
  className?: string;
}

export const InlineLoader: React.FC<InlineLoaderProps> = ({
  message = 'Loading…',
  size = 14,
  className = '',
}) => {
  return (
    <div
      className={`flex items-center gap-2 text-sm ${className}`}
      style={{ color: 'var(--color-text-muted)' }}
      role="status"
      aria-live="polite"
    >
      <Spinner size={size} />
      <span>{message}</span>
    </div>
  );
};

export const SpinnerOverlay: React.FC<{ message?: string }> = ({ message }) => {
  return (
    <div
      className="fixed inset-0 flex flex-col items-center justify-center z-50"
      style={{
        background: 'rgba(15, 23, 42, 0.7)',
      }}
    >
      <Spinner size={48} />
      {message && (
        <p
          className="mt-4"
          style={{
            color: 'var(--color-text)',
            fontSize: '14px',
          }}
        >
          {message}
        </p>
      )}
    </div>
  );
};
