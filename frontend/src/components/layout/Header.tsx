import React from 'react';
import { useAppStore } from '../../store/appStore';
import { useAuthStore } from '../../store/authStore';
import { useTheme } from '../../hooks/useTheme';

export const Header: React.FC = () => {
  const { selectedWell, toggleSidebar } = useAppStore();
  const { user, logout } = useAuthStore();
  const { theme, toggleTheme } = useTheme();

  return (
    <header
      className="fixed top-0 left-0 right-0 z-50 flex items-center justify-between"
      style={{
        backgroundColor: 'var(--surface)',
        borderBottom: '1px solid var(--border)',
        padding: '12px 24px',
      }}
    >
      {/* Left: hamburger + app title */}
      <div className="flex items-center gap-4">
        <button
          onClick={toggleSidebar}
          className="p-1.5 rounded-md transition-colors"
          style={{ color: 'var(--text-muted)' }}
          onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--hover)')}
          onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
          aria-label="Toggle sidebar"
        >
          <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M4 6h16M4 12h16M4 18h16" />
          </svg>
        </button>

        <div className="flex items-center gap-3">
          <svg className="w-7 h-7" fill="none" stroke="currentColor" viewBox="0 0 24 24" style={{ color: 'var(--primary)' }}>
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
              d="M3 13h2v8H3zm6-4h2v12H9zm6-6h2v18h-2zm6 10h2v8h-2z" />
          </svg>
          <div>
            <h1 className="text-base font-semibold" style={{ color: 'var(--text-primary)' }}>
              Drilling Data Visualization
            </h1>
            {selectedWell && (
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>{selectedWell.well_name}</p>
            )}
          </div>
        </div>
      </div>

      {/* Right: theme toggle + user info + logout */}
      <div className="flex items-center gap-3">
        <button
          onClick={toggleTheme}
          className="transition-all"
          style={{
            padding: '6px 10px',
            background: 'none',
            border: '1px solid var(--border)',
            borderRadius: 'var(--radius)',
            fontSize: '16px',
            cursor: 'pointer',
            color: 'var(--text-muted)',
          }}
          onMouseEnter={(e) => {
            e.currentTarget.style.backgroundColor = 'var(--hover)';
            e.currentTarget.style.borderColor = 'var(--primary)';
          }}
          onMouseLeave={(e) => {
            e.currentTarget.style.backgroundColor = 'transparent';
            e.currentTarget.style.borderColor = 'var(--border)';
          }}
          title={`Switch to ${theme === 'dark' ? 'light' : 'dark'} mode`}
        >
          {theme === 'dark' ? '☀️' : '🌙'}
        </button>

        {user && (
          <>
            <div className="text-right">
              <p className="text-sm font-medium" style={{ color: 'var(--text-primary)' }}>
                {user.full_name || user.username}
              </p>
              <p className="text-xs" style={{ color: 'var(--text-muted)' }}>
                {user.is_admin ? 'Admin' : 'User'}
              </p>
            </div>
            <div
              className="w-8 h-8 rounded-full flex items-center justify-center text-sm font-medium"
              style={{ backgroundColor: 'var(--primary)', color: '#ffffff' }}
            >
              {user.username.charAt(0).toUpperCase()}
            </div>
            <button
              onClick={logout}
              className="p-1.5 rounded-md transition-colors"
              style={{ color: 'var(--text-muted)' }}
              onMouseEnter={(e) => (e.currentTarget.style.backgroundColor = 'var(--hover)')}
              onMouseLeave={(e) => (e.currentTarget.style.backgroundColor = 'transparent')}
              title="Logout"
            >
              <svg className="w-5 h-5" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                  d="M17 16l4-4m0 0l-4-4m4 4H7m6 4v1a3 3 0 01-3 3H6a3 3 0 01-3-3V7a3 3 0 013-3h4a3 3 0 013 3v1" />
              </svg>
            </button>
          </>
        )}
      </div>
    </header>
  );
};
