/** @type {import('tailwindcss').Config} */
export default {
  content: [
    "./src/**/*.{ts,tsx}",
    "../templates/**/*.html",
  ],
  safelist: [
    { pattern: /^tier-(low|medium|high|critical|unknown)$/ },
    { pattern: /^rate-(strong|mid|weak|na)$/ },
    { pattern: /^score-(strong|mid|weak)$/ },
    { pattern: /^status-(ok|fail|skip)$/ },
    { pattern: /^badge(-[a-z]+)?$/ },
    "staleness-pill",
    "staleness-warn",
    { pattern: /^ref-delta-(pos|neg|neutral)$/ },
    "row-warn",
  ],
  theme: {
    extend: {
      colors: {
        surface: "#faf9f7",
        "surface-raised": "#ffffff",
        "surface-muted": "#f3f2ef",
        border: "#e8e6e1",
        "duke-blue": "#012169",
        "duke-blue-hover": "#001a57",
        "duke-blue-muted": "#e8edf7",
        text: "#1a1a18",
        "text-muted": "#5c5a54",
        "text-subtle": "#8a877f",
        stale: "#d97706",
        "private-accent": "#7c3aed",
        "private-bg": "#f5f3ff",
      },
      fontFamily: {
        sans: [
          "ui-sans-serif",
          "system-ui",
          "-apple-system",
          "Segoe UI",
          "Roboto",
          "Helvetica Neue",
          "Arial",
          "sans-serif",
        ],
        mono: ["ui-monospace", "SFMono-Regular", "Menlo", "Monaco", "Consolas", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgb(26 26 24 / 0.04), 0 4px 12px rgb(26 26 24 / 0.06)",
        elevated: "0 4px 16px rgb(26 26 24 / 0.08)",
      },
    },
  },
  plugins: [],
};
