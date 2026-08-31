import type { Config } from "tailwindcss";

// Every color here is a CSS custom property from app/tokens.css. Components
// use Tailwind classes (bg-surface, text-text-primary, border-border, ...);
// nobody writes a hex value in a component file.
const config: Config = {
  content: ["./app/**/*.{ts,tsx}", "./components/**/*.{ts,tsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["var(--font-inter)", "system-ui", "sans-serif"],
      },
      fontWeight: {
        // Only 400 and 500 exist in this design system -- normal/medium.
        normal: "400",
        medium: "500",
      },
      colors: {
        bg: "var(--bg)",
        surface: "var(--surface)",
        "surface-raised": "var(--surface-raised)",
        border: "var(--border)",
        "border-strong": "var(--border-strong)",
        "text-primary": "var(--text-primary)",
        "text-secondary": "var(--text-secondary)",
        "text-muted": "var(--text-muted)",
        accent: "var(--accent)",
        "accent-dim": "var(--accent-dim)",
        action: "var(--action)",
        "action-text": "var(--action-text)",
        "sev-high": "var(--sev-high)",
        "sev-medium": "var(--sev-medium)",
        "sev-low": "var(--sev-low)",
      },
      maxWidth: {
        content: "var(--content-max-width)",
      },
      borderRadius: {
        card: "var(--radius-card)",
      },
      fontSize: {
        eyebrow: [
          "11px",
          { letterSpacing: "0.12em", lineHeight: "1.4", fontWeight: "500" },
        ],
      },
      letterSpacing: {
        tight2: "-0.02em",
      },
    },
  },
  plugins: [],
};

export default config;
