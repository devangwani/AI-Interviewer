/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        // "white" is repurposed as the primary foreground token per theme.
        // bg-white/5, border-white/10, text-white etc. all become theme-aware.
        white: "rgb(var(--c-white) / <alpha-value>)",

        brand: {
          50:  "#eef2ff",
          100: "#e0e7ff",
          300: "rgb(var(--c-brand-300) / <alpha-value>)",
          400: "rgb(var(--c-brand-400) / <alpha-value>)",
          500: "rgb(var(--c-brand-500) / <alpha-value>)",
          600: "rgb(var(--c-brand-600) / <alpha-value>)",
          700: "rgb(var(--c-brand-700) / <alpha-value>)",
          900: "rgb(var(--c-brand-900) / <alpha-value>)",
        },

        surface: {
          500: "rgb(var(--c-surface-500) / <alpha-value>)",
          600: "rgb(var(--c-surface-600) / <alpha-value>)",
          700: "rgb(var(--c-surface-700) / <alpha-value>)",
          800: "rgb(var(--c-surface-800) / <alpha-value>)",
          900: "rgb(var(--c-surface-900) / <alpha-value>)",
        },

        // Slate is used everywhere for body text — theme each shade.
        slate: {
          100: "rgb(var(--c-slate-100) / <alpha-value>)",
          200: "rgb(var(--c-slate-200) / <alpha-value>)",
          300: "rgb(var(--c-slate-300) / <alpha-value>)",
          400: "rgb(var(--c-slate-400) / <alpha-value>)",
          500: "rgb(var(--c-slate-500) / <alpha-value>)",
          600: "rgb(var(--c-slate-600) / <alpha-value>)",
          700: "#334155",
          800: "#1e293b",
          900: "#0f172a",
        },
      },

      fontFamily: {
        sans: ["Inter", "ui-sans-serif", "system-ui"],
        mono: ["JetBrains Mono", "ui-monospace"],
      },

      boxShadow: {
        // References CSS vars so glow colour changes per theme.
        glow:    "var(--shadow-glow)",
        "glow-sm": "var(--shadow-glow-sm)",
      },

      animation: {
        "pulse-slow": "pulse 3s cubic-bezier(0.4,0,0.6,1) infinite",
        "fade-in":    "fadeIn 0.4s ease forwards",
        "slide-up":   "slideUp 0.4s ease forwards",
      },
      keyframes: {
        fadeIn:  { from: { opacity: 0 },                          to: { opacity: 1 } },
        slideUp: { from: { opacity: 0, transform: "translateY(16px)" }, to: { opacity: 1, transform: "translateY(0)" } },
      },
    },
  },
  plugins: [],
};
