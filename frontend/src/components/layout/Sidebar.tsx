import React from 'react';
import { useAppStore } from '../../store/appStore';
import { Link, useLocation } from 'react-router-dom';

interface NavItem {
  name: string;
  icon: React.ReactNode;
  path: string;
  active?: boolean;
}

export const Sidebar: React.FC = () => {
  const { sidebarOpen } = useAppStore();
  const location = useLocation();
  const currentPath = location.pathname;

  const navItems: NavItem[] = [
    {
      name: 'Wells',
      path: '/wells',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M19 11H5m14 0a2 2 0 012 2v6a2 2 0 01-2 2H5a2 2 0 01-2-2v-6a2 2 0 012-2m14 0V9a2 2 0 00-2-2M5 11V9a2 2 0 012-2m0 0V5a2 2 0 012-2h6a2 2 0 012 2v2M7 7h10" />
        </svg>
      ),
      active: currentPath.startsWith('/wells') && !currentPath.includes('/logs'),
    },
    {
      name: 'Quality Report',
      path: '/quality',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 17v-2a2 2 0 012-2h2a2 2 0 012 2v2m-8 0h8m-8 0a2 2 0 01-2-2V7a2 2 0 012-2h8a2 2 0 012 2v8a2 2 0 01-2 2" />
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 9h6m-6 4h6" />
        </svg>
      ),
      active: currentPath === '/quality' || currentPath.includes('/wells/') && currentPath.includes('/quality'),
    },
    {
      name: 'Outlier Detection',
      path: '/outliers',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M12 9l2 2-2 2m4-2a4 4 0 11-8 0 4 4 0 018 0z"
          />
          <path
            strokeLinecap="round"
            strokeLinejoin="round"
            strokeWidth={2}
            d="M4.93 4.93l2.12 2.12M16.95 16.95l2.12 2.12M2 12h3m14 0h3M6.34 17.66l-2.12 2.12M17.66 6.34l2.12-2.12"
          />
        </svg>
      ),
      active: currentPath.startsWith('/outliers'),
    },
    {
      name: 'Well Logs',
      path: '/logs',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
        </svg>
      ),
      active: currentPath === '/logs',
    },
    {
      name: 'Comparison',
      path: '/comparison',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 19v-6a2 2 0 00-2-2H5a2 2 0 00-2 2v6a2 2 0 002 2h2a2 2 0 002-2zm0 0V9a2 2 0 012-2h2a2 2 0 012 2v10m-6 0a2 2 0 002 2h2a2 2 0 002-2m0 0V5a2 2 0 012-2h2a2 2 0 012 2v14a2 2 0 01-2 2h-2a2 2 0 01-2-2z" />
        </svg>
      ),
      active: currentPath === '/comparison',
    },
    {
      name: 'Crossplots',
      path: '/crossplots',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M7 12l3-3 3 3 4-4M8 21l4-4 4 4M3 4h18M4 4h16v12a1 1 0 01-1 1H5a1 1 0 01-1-1V4z" />
        </svg>
      ),
      active: currentPath === '/crossplots',
    },
    {
      name: 'Cases',
      path: '/cases',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M9 5H7a2 2 0 00-2 2v12a2 2 0 002 2h10a2 2 0 002-2V7a2 2 0 00-2-2h-2M9 5a2 2 0 002 2h2a2 2 0 002-2M9 5a2 2 0 012-2h2a2 2 0 012 2m-6 9l2 2 4-4" />
        </svg>
      ),
      active: currentPath === '/cases',
    },
    {
      name: 'Users',
      path: '/users',
      icon: (
        <svg className="w-[18px] h-[18px]" fill="none" stroke="currentColor" viewBox="0 0 24 24">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
            d="M12 4.354a4 4 0 110 5.292M15 21H3v-1a6 6 0 0112 0v1zm0 0h6v-1a6 6 0 00-9-5.197M13 7a4 4 0 11-8 0 4 4 0 018 0z" />
        </svg>
      ),
      active: currentPath === '/users',
    },
  ];

  if (!sidebarOpen) {
    return null;
  }

  return (
    <aside
      className="fixed left-0 bottom-0 flex flex-col z-40"
      style={{
        top: '56px',
        width: '200px',
        backgroundColor: 'var(--surface)',
        borderRight: '1px solid var(--border)',
      }}
    >
      <nav className="flex-1 px-3 py-4 space-y-1">
        {navItems.map((item) => (
          <Link
            key={item.path}
            to={item.path}
            className="flex items-center gap-3 px-3 py-2 text-sm font-medium transition-colors"
            style={{
              borderRadius: '6px',
              color: item.active ? 'var(--primary)' : 'var(--text-muted)',
              backgroundColor: item.active ? 'rgba(74, 124, 255, 0.12)' : 'transparent',
            }}
            onMouseEnter={(e) => {
              if (!item.active) {
                e.currentTarget.style.backgroundColor = 'var(--hover)';
                e.currentTarget.style.color = 'var(--text-primary)';
              }
            }}
            onMouseLeave={(e) => {
              if (!item.active) {
                e.currentTarget.style.backgroundColor = 'transparent';
                e.currentTarget.style.color = 'var(--text-muted)';
              }
            }}
          >
            {item.icon}
            <span>{item.name}</span>
          </Link>
        ))}
      </nav>
    </aside>
  );
};
