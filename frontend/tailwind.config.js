/** @type {import('tailwindcss').Config} */
export default {
  darkMode: 'class',
  content: [
    "./index.html",
    "./src/**/*.{js,jsx,ts,tsx}",
  ],
  theme: {
    extend: {
      colors: {
        'neon-green': '#00ff88',
        'neon-cyan': '#00e5ff',
        'neon-red': '#ff3366',
        'dark-bg': '#0a0e17',
        'card-bg': '#111827',
        'surface': '#1e293b',
      },
      backgroundColor: {
        'dark': '#0a0e17',
        'darker': '#050609',
      },
      textColor: {
        'muted': '#94a3b8',
        'bright': '#f1f5f9',
      },
      boxShadow: {
        'neon-green': '0 0 20px rgba(0, 255, 136, 0.5)',
        'neon-cyan': '0 0 20px rgba(0, 229, 255, 0.5)',
        'neon-red': '0 0 20px rgba(255, 51, 102, 0.5)',
      },
      animation: {
        'pulse-neon': 'pulse-neon 2s cubic-bezier(0.4, 0, 0.6, 1) infinite',
        'glow': 'glow 2s ease-in-out infinite',
      },
      keyframes: {
        'pulse-neon': {
          '0%, 100%': { opacity: '1' },
          '50%': { opacity: '0.7' },
        },
        'glow': {
          '0%, 100%': { boxShadow: '0 0 5px rgba(0, 255, 136, 0.5)' },
          '50%': { boxShadow: '0 0 20px rgba(0, 255, 136, 0.8)' },
        },
      },
      borderColor: {
        'grid': '#1e293b',
      },
    },
  },
  plugins: [],
}
