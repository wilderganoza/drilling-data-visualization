import React from 'react';

export interface Tab {
  id: string;
  label: string;
  icon?: React.ReactNode;
}

export interface TabsProps {
  tabs: Tab[];
  activeTab: string;
  onTabChange: (tabId: string) => void;
  variant?: 'default' | 'results';
  className?: string;
}

export const Tabs: React.FC<TabsProps> = ({
  tabs,
  activeTab,
  onTabChange,
  variant = 'default',
  className = '',
}) => {
  if (variant === 'results') {
    return (
      <div
        className={`flex gap-0 mb-5 ${className}`}
        style={{
          borderBottom: '2px solid var(--color-border)',
        }}
      >
        {tabs.map((tab) => (
          <button
            key={tab.id}
            onClick={() => onTabChange(tab.id)}
            className="transition-all"
            style={{
              padding: '10px 20px',
              background: 'none',
              border: 'none',
              borderBottom: '2px solid transparent',
              marginBottom: '-2px',
              color: tab.id === activeTab ? 'var(--color-primary)' : 'var(--color-text-muted)',
              fontSize: '13px',
              fontWeight: tab.id === activeTab ? 600 : 500,
              cursor: 'pointer',
              whiteSpace: 'nowrap',
            }}
            onMouseEnter={(e) => {
              if (tab.id !== activeTab) {
                e.currentTarget.style.background = 'rgba(255,255,255,0.03)';
                e.currentTarget.style.color = 'var(--color-text)';
              }
            }}
            onMouseLeave={(e) => {
              if (tab.id !== activeTab) {
                e.currentTarget.style.background = 'none';
                e.currentTarget.style.color = 'var(--color-text-muted)';
              }
            }}
          >
            {tab.icon && <span style={{ marginRight: '6px' }}>{tab.icon}</span>}
            {tab.label}
          </button>
        ))}
      </div>
    );
  }

  return (
    <div
      className={`flex gap-1 mb-4 ${className}`}
      style={{
        borderBottom: '1px solid var(--color-border)',
        paddingBottom: 0,
      }}
    >
      {tabs.map((tab) => (
        <button
          key={tab.id}
          onClick={() => onTabChange(tab.id)}
          className="transition-all"
          style={{
            padding: '8px 16px',
            background: 'none',
            border: 'none',
            borderBottom: '2px solid transparent',
            color: tab.id === activeTab ? 'var(--color-primary)' : 'var(--color-text-muted)',
            fontSize: '13px',
            fontWeight: 500,
            cursor: 'pointer',
            borderBottomColor: tab.id === activeTab ? 'var(--color-primary)' : 'transparent',
          }}
          onMouseEnter={(e) => {
            if (tab.id !== activeTab) {
              e.currentTarget.style.color = 'var(--color-text)';
            }
          }}
          onMouseLeave={(e) => {
            if (tab.id !== activeTab) {
              e.currentTarget.style.color = 'var(--color-text-muted)';
            }
          }}
        >
          {tab.icon && <span style={{ marginRight: '6px' }}>{tab.icon}</span>}
          {tab.label}
        </button>
      ))}
    </div>
  );
};
