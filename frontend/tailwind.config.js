/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        ds: {
          bg: '#0f1117',
          surface: '#1a1d27',
          hover: '#232733',
          border: '#2a2e3a',
          'border-focus': '#4a7cff',
          'text-primary': '#e4e6ed',
          'text-muted': '#8b8fa3',
          primary: '#4a7cff',
          'primary-hover': '#3a6aee',
          success: '#34d399',
          warning: '#fbbf24',
          danger: '#f87171',
        },
      },
      fontFamily: {
        sans: ['Inter', '-apple-system', 'BlinkMacSystemFont', 'Segoe UI', 'sans-serif'],
      },
      borderRadius: {
        ds: '8px',
        'ds-lg': '12px',
      },
    },
  },
  plugins: [],
}
