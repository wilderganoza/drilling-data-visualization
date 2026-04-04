import React, { useState } from 'react';
import { useNavigate } from 'react-router-dom';
import { login } from '../api/endpoints/auth';
import { useAuthStore } from '../store/authStore';

export const Login: React.FC = () => {
  const [username, setUsername] = useState('');
  const [password, setPassword] = useState('');
  const [error, setError] = useState('');
  const [loading, setLoading] = useState(false);
  const navigate = useNavigate();
  const setAuth = useAuthStore((s) => s.setAuth);

  const handleSubmit = async (e: React.FormEvent) => {
    e.preventDefault();
    setError('');
    setLoading(true);
    try {
      const response = await login({ username, password });
      setAuth(response.access_token, response.user);
      navigate('/');
    } catch (err: any) {
      const detail = err?.response?.data?.detail;
      setError(typeof detail === 'string' ? detail : 'Invalid username or password');
    } finally {
      setLoading(false);
    }
  };

  return (
    <div className="min-h-screen flex items-center justify-center px-4" style={{ backgroundColor: 'var(--bg)' }}>
      <div className="w-full" style={{ maxWidth: '400px' }}>
        {/* Logo / Title */}
        <div className="text-center mb-8">
          <div
            className="inline-flex items-center justify-center w-14 h-14 mb-4"
            style={{ backgroundColor: 'var(--primary)', borderRadius: 'var(--radius-lg)' }}
          >
            <svg className="w-7 h-7 text-white" fill="none" stroke="currentColor" viewBox="0 0 24 24">
              <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2}
                d="M3 13h2v8H3zm6-4h2v12H9zm6-6h2v18h-2zm6 10h2v8h-2z" />
            </svg>
          </div>
          <h1 className="text-2xl font-bold" style={{ color: 'var(--text-primary)' }}>
            Drilling Data Visualization
          </h1>
          <p className="mt-1 text-sm" style={{ color: 'var(--text-muted)' }}>Sign in to your account</p>
        </div>

        {/* Login Form */}
        <form
          onSubmit={handleSubmit}
          className="p-8 space-y-6"
          style={{
            backgroundColor: 'var(--surface)',
            borderRadius: 'var(--radius-lg)',
            border: '1px solid var(--border)',
            boxShadow: '0 4px 24px rgba(0, 0, 0, 0.3)',
          }}
        >
          {error && (
            <div
              className="px-4 py-3 text-sm"
              style={{
                backgroundColor: 'rgba(248, 113, 113, 0.1)',
                border: '1px solid rgba(248, 113, 113, 0.3)',
                borderRadius: 'var(--radius)',
                color: 'var(--danger)',
              }}
            >
              {error}
            </div>
          )}

          <div>
            <label htmlFor="username" className="block text-sm font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
              Username
            </label>
            <input
              id="username"
              type="text"
              value={username}
              onChange={(e) => setUsername(e.target.value)}
              required
              autoFocus
              className="w-full text-sm outline-none transition-colors"
              style={{
                padding: '8px 12px',
                backgroundColor: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                color: 'var(--text-primary)',
              }}
              onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--border-focus)')}
              onBlur={(e) => (e.currentTarget.style.borderColor = 'var(--border)')}
              placeholder="Enter your username"
            />
          </div>

          <div>
            <label htmlFor="password" className="block text-sm font-medium mb-2" style={{ color: 'var(--text-primary)' }}>
              Password
            </label>
            <input
              id="password"
              type="password"
              value={password}
              onChange={(e) => setPassword(e.target.value)}
              required
              className="w-full text-sm outline-none transition-colors"
              style={{
                padding: '8px 12px',
                backgroundColor: 'var(--bg)',
                border: '1px solid var(--border)',
                borderRadius: 'var(--radius)',
                color: 'var(--text-primary)',
              }}
              onFocus={(e) => (e.currentTarget.style.borderColor = 'var(--border-focus)')}
              onBlur={(e) => (e.currentTarget.style.borderColor = 'var(--border)')}
              placeholder="Enter your password"
            />
          </div>

          <button
            type="submit"
            disabled={loading}
            className="w-full py-2.5 px-4 text-sm font-medium text-white transition-colors disabled:opacity-50 disabled:cursor-not-allowed"
            style={{
              backgroundColor: 'var(--primary)',
              borderRadius: 'var(--radius)',
            }}
            onMouseEnter={(e) => { if (!loading) e.currentTarget.style.backgroundColor = 'var(--primary-hover)'; }}
            onMouseLeave={(e) => { e.currentTarget.style.backgroundColor = 'var(--primary)'; }}
          >
            {loading ? 'Signing in...' : 'Sign In'}
          </button>
        </form>
      </div>
    </div>
  );
};
