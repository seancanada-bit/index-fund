/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./src/**/*.{js,jsx,ts,tsx}", "./public/index.html"],
  theme: {
    extend: {
      colors: {
        navy: {
          950: "#0a0e1a",
          900: "#0d1120",
          800: "#111827",
          700: "#1f2937",
          600: "#374151",
        },
        emerald: { DEFAULT: "#10b981" },
        crimson: { DEFAULT: "#ef4444" },
        amber: { DEFAULT: "#f59e0b" },
      },
      fontFamily: {
        mono: ["IBM Plex Mono", "monospace"],
        sans: ["DM Sans", "sans-serif"],
      },
    },
  },
  plugins: [],
};
