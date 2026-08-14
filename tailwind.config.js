/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      colors: {
        ink: '#09090e',
        panel: '#12121c',
        line: '#242436',
        accent: '#22d3ee',
        cyanGlow: '#06b6d4',
        fuchsiaGlow: '#d946ef',
      },
      boxShadow: {
        glow: '0 0 80px rgba(34, 211, 238, 0.18)',
        neon: '0 0 40px rgba(217, 70, 239, 0.25)',
      },
      fontFamily: {
        sans: ['Inter', 'ui-sans-serif', 'system-ui'],
      },
    },
  },
  plugins: [],
}
