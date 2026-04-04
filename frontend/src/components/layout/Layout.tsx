import React from 'react';
import { Header } from './Header';
import { Sidebar } from './Sidebar';
import { ToastContainer } from '../notifications';
import { useAppStore } from '../../store/appStore';

interface LayoutProps {
  children: React.ReactNode;
}

export const Layout: React.FC<LayoutProps> = ({ children }) => {
  const { sidebarOpen } = useAppStore();

  return (
    <div className="min-h-screen" style={{ backgroundColor: 'var(--bg)' }}>
      <Header />
      <div className="flex">
        <Sidebar />
        <main
          className="flex-1 p-6 overflow-auto min-h-screen transition-all duration-300"
          style={{
            marginLeft: sidebarOpen ? '200px' : '0',
            marginTop: '56px',
          }}
        >
          {children}
        </main>
      </div>
      <ToastContainer />
    </div>
  );
};
