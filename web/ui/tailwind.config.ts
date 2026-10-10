import type { Config } from "tailwindcss";

/**
 * Offlineify design tokens.
 *
 * Everything visual should come from here or from components/ui/*, never from
 * raw Tailwind palette classes. If a color or size needs to change, change it
 * in this file (or the component) and the whole app follows.
 */
const config: Config = {
  content: [
    "./pages/**/*.{js,ts,jsx,tsx,mdx}",
    "./components/**/*.{js,ts,jsx,tsx,mdx}",
    "./app/**/*.{js,ts,jsx,tsx,mdx}",
  ],
  theme: {
    extend: {
      colors: {
        // Spotify's green, as the single accent.
        accent: {
          DEFAULT: "#1ed760",
          hover: "#3be477",
          pressed: "#169c46",
          muted: "#1db954",
          faint: "rgba(30, 215, 96, 0.12)",
        },
        // Surfaces, layered the way Spotify layers them (base -> raised -> overlay).
        surface: {
          base: "#121212",    // page background
          raised: "#181818",  // cards ("cards on black", elevated)
          overlay: "#1f1f1f", // hover states, bars
          input: "#242424",   // form controls
        },
        // Dividers; Spotify uses faint lines, not hard borders.
        line: {
          DEFAULT: "#2a2a2a",
          strong: "#727272",
        },
        // Text hierarchy from Spotify's type scale.
        content: {
          DEFAULT: "#ffffff",
          muted: "#b3b3b3",   // secondary text
          faint: "#7a7a7a",
          disabled: "#5a5a5a",
        },
        // Status colors (job states, banners).
        danger: {
          DEFAULT: "#e91429",
          hover: "#f4364c",
          faint: "rgba(233, 20, 41, 0.12)",
        },
        warning: {
          DEFAULT: "#ffa42b",
          hover: "#ffb95c",
          faint: "rgba(255, 164, 43, 0.12)",
        },
      },
      borderRadius: {
        control: "0.5rem", // buttons, inputs, small controls
        card: "1rem",      // cards and panels
      },
      fontFamily: {
        sans: ["var(--font-sans)", "system-ui", "sans-serif"],
        mono: ["var(--font-mono)", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      maxWidth: {
        page: "80rem", // the one page container width
      },
    },
  },
  plugins: [],
};
export default config;
