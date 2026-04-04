import React, { useEffect } from 'react';

export interface ModalProps {
  isOpen: boolean;
  onClose: () => void;
  children: React.ReactNode;
  maxWidth?: string;
}

export const Modal: React.FC<ModalProps> = ({
  isOpen,
  onClose,
  children,
  maxWidth = '460px',
}) => {
  useEffect(() => {
    const handleEscape = (e: KeyboardEvent) => {
      if (e.key === 'Escape') onClose();
    };

    if (isOpen) {
      document.addEventListener('keydown', handleEscape);
      document.body.style.overflow = 'hidden';
    }

    return () => {
      document.removeEventListener('keydown', handleEscape);
      document.body.style.overflow = 'unset';
    };
  }, [isOpen, onClose]);

  if (!isOpen) return null;

  return (
    <div
      className="fixed inset-0 flex items-center justify-center z-50"
      style={{
        background: 'rgba(15, 23, 42, 0.55)',
        padding: '24px',
      }}
      onClick={onClose}
    >
      <div
        onClick={(e) => e.stopPropagation()}
        style={{
          background: 'var(--color-surface)',
          borderRadius: '12px',
          border: '1px solid var(--color-border)',
          width: '100%',
          maxWidth,
          boxShadow: '0 20px 40px rgba(15, 23, 42, 0.35)',
        }}
      >
        {children}
      </div>
    </div>
  );
};

export interface ModalHeaderProps {
  children: React.ReactNode;
  onClose?: () => void;
}

export const ModalHeader: React.FC<ModalHeaderProps> = ({ children, onClose }) => {
  return (
    <div
      className="flex items-center justify-between"
      style={{
        padding: '16px 20px',
        borderBottom: '1px solid var(--color-border)',
      }}
    >
      <h3
        style={{
          fontSize: '18px',
          fontWeight: 600,
          color: 'var(--color-text)',
        }}
      >
        {children}
      </h3>
      {onClose && (
        <button
          onClick={onClose}
          className="transition-colors"
          style={{
            background: 'none',
            border: 'none',
            color: 'var(--color-text-muted)',
            cursor: 'pointer',
            padding: '4px',
            fontSize: '20px',
            lineHeight: 1,
          }}
          onMouseEnter={(e) => (e.currentTarget.style.color = 'var(--color-text)')}
          onMouseLeave={(e) => (e.currentTarget.style.color = 'var(--color-text-muted)')}
        >
          ×
        </button>
      )}
    </div>
  );
};

export interface ModalBodyProps {
  children: React.ReactNode;
}

export const ModalBody: React.FC<ModalBodyProps> = ({ children }) => {
  return (
    <div style={{ padding: '0 20px 20px' }}>
      {children}
    </div>
  );
};

export interface ModalFooterProps {
  children: React.ReactNode;
}

export const ModalFooter: React.FC<ModalFooterProps> = ({ children }) => {
  return (
    <div
      className="flex justify-end gap-2"
      style={{
        padding: '16px 20px',
        borderTop: '1px solid var(--color-border)',
      }}
    >
      {children}
    </div>
  );
};
