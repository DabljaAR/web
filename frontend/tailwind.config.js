/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./index.html",
    "./src/**/*.{js,ts,jsx,tsx}",
  ],
  theme: {
    extend: {
      // ─── DabljaAR Brand Colors ───────────────────────────────────────────
      colors: {
        brand: {
          // Primary — Indigo gradient range
          primary:   '#4338CA', // Indigo 700
          secondary: '#7C3AED', // Violet 600
          // AR accent — Amber (Arabic cultural warmth)
          accent:    '#D97706', // Amber 600
          'accent-light': '#F59E0B', // Amber 500 (dark-bg variant)
          // Deep dark
          dark:      '#1E1B4B', // Indigo 950
          // Soft tints
          tint:      '#E0E7FF', // Indigo 100
          'tint-light': '#F1F5F9', // Slate 100
        },
        // Semantic aliases
        success: '#059669', // Emerald 600
        warning: '#D97706', // Amber 600
        danger:  '#DC2626', // Red 600
        info:    '#0891B2', // Cyan 600
      },

      // ─── Typography ──────────────────────────────────────────────────────
      fontFamily: {
        display: ['Cairo', 'system-ui', 'sans-serif'],  // headings, logo
        body:    ['Inter', 'system-ui', 'sans-serif'],   // body text
        mono:    ['JetBrains Mono', 'Menlo', 'monospace'], // code, timestamps
      },

      // ─── Brand gradient ──────────────────────────────────────────────────
      backgroundImage: {
        'brand-gradient': 'linear-gradient(135deg, #4338CA 0%, #7C3AED 100%)',
        'brand-gradient-amber': 'linear-gradient(135deg, #4338CA 0%, #D97706 100%)',
      },

      // ─── Border radius ───────────────────────────────────────────────────
      borderRadius: {
        brand: '14px', // matches icon mark corner radius
      },
    },
  },
  plugins: [],
}

