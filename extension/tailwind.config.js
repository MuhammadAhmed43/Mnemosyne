/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./**/*.{tsx,ts,html}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        // Polished, professional dark theme (slate base + refined royal-blue accent),
        // tuned so button text and labels clear WCAG AA.
        bg: { primary: "#0D1117", secondary: "#161B22", tertiary: "#1C232E", hover: "#232E3D" },
        border: { DEFAULT: "#2A3340", strong: "#3B4757" },
        accent: { DEFAULT: "#3A66D6", hover: "#2E52B0" },
        text: { primary: "#E6EAF2", secondary: "#9BA6B8", tertiary: "#7E8A9E" },
        success: "#34D399",
        warning: "#F5A623",
        danger: "#F0506B",
        info: "#4D7CFE",
        node: {
          goal: "#34D399", decision: "#818CF8", task: "#60A5FA", problem: "#FB7185",
          entity: "#FBBF24", preference: "#F472B6", fact: "#94A3B8", event: "#2DD4BF",
          insight: "#A78BFA", note: "#38BDF8",
        },
      },
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
        mono: ["JetBrains Mono", "monospace"],
      },
    },
  },
  plugins: [],
}
