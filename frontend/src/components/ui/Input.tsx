import React from 'react';

export interface InputProps extends React.InputHTMLAttributes<HTMLInputElement> {
  label?: string;
  error?: string;
  helperText?: string;
}

export const Input: React.FC<InputProps> = ({
  label,
  error,
  helperText,
  className = '',
  id,
  ...props
}) => {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-sm font-medium mb-1"
          style={{ color: 'var(--text-primary)' }}
        >
          {label}
        </label>
      )}
      <input
        id={inputId}
        className={`w-full text-sm outline-none transition-colors ${className}`}
        style={{
          padding: '8px 12px',
          backgroundColor: 'var(--bg)',
          border: `1px solid ${error ? 'var(--danger)' : 'var(--border)'}`,
          borderRadius: 'var(--radius)',
          color: 'var(--text-primary)',
          boxShadow: '0 0 0 0 rgba(0,0,0,0)',
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = error ? 'var(--danger)' : 'var(--color-primary)';
          e.currentTarget.style.boxShadow = error
            ? '0 0 0 2px rgba(248, 113, 113, 0.18)'
            : '0 0 0 2px rgba(74, 124, 255, 0.18)';
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = error ? 'var(--danger)' : 'var(--border)';
          e.currentTarget.style.boxShadow = '0 0 0 0 rgba(0,0,0,0)';
        }}
        {...props}
      />
      {error && (
        <p className="mt-1 text-xs" style={{ color: 'var(--danger)' }}>{error}</p>
      )}
      {helperText && !error && (
        <p className="mt-1 text-xs" style={{ color: 'var(--text-muted)' }}>{helperText}</p>
      )}
    </div>
  );
};

export interface SelectProps extends React.SelectHTMLAttributes<HTMLSelectElement> {
  label?: string;
  error?: string;
  options: Array<{ value: string | number; label: string }>;
}

export const Select: React.FC<SelectProps> = ({
  label,
  error,
  options,
  className = '',
  id,
  ...props
}) => {
  const inputId = id || label?.toLowerCase().replace(/\s+/g, '-');

  return (
    <div className="w-full">
      {label && (
        <label
          htmlFor={inputId}
          className="block text-sm font-medium mb-1"
          style={{ color: 'var(--text-primary)' }}
        >
          {label}
        </label>
      )}
      <select
        id={inputId}
        className={`w-full text-sm outline-none transition-colors ${className}`}
        style={{
          padding: '8px 12px',
          backgroundColor: 'var(--color-surface)',
          border: `1px solid ${error ? 'var(--danger)' : 'var(--border)'}`,
          borderRadius: 'var(--radius)',
          color: 'var(--color-text)',
          boxShadow: '0 0 0 0 rgba(0,0,0,0)',
        }}
        onFocus={(e) => {
          e.currentTarget.style.borderColor = error ? 'var(--danger)' : 'var(--color-primary)';
          e.currentTarget.style.boxShadow = error
            ? '0 0 0 2px rgba(248, 113, 113, 0.18)'
            : '0 0 0 2px rgba(74, 124, 255, 0.18)';
        }}
        onBlur={(e) => {
          e.currentTarget.style.borderColor = error ? 'var(--danger)' : 'var(--border)';
          e.currentTarget.style.boxShadow = '0 0 0 0 rgba(0,0,0,0)';
        }}
        {...props}
      >
        {options.map((option) => (
          <option key={option.value} value={option.value}>
            {option.label}
          </option>
        ))}
      </select>
      {error && (
        <p className="mt-1 text-xs" style={{ color: 'var(--danger)' }}>{error}</p>
      )}
    </div>
  );
};
