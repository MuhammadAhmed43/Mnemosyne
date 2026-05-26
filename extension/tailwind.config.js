/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./**/*.{tsx,ts,html}"],
  darkMode: "class",
  theme: {
    extend: {
      colors: {
        bg: { primary: "#0A0A0F", secondary: "#111118", tertiary: "#1A1A24", hover: "#1E1E2E" },
        border: { DEFAULT: "#2A2A3A", strong: "#3A3A4E" },
        accent: { DEFAULT: "#7C3AED", hover: "#6D28D9" },
        text: { primary: "#F0F0F5", secondary: "#8B8BA7", tertiary: "#7A7A92" },
        success: "#10B981",
        warning: "#F59E0B",
        danger: "#EF4444",
        info: "#3B82F6",
        node: {
          goal: "#10B981", decision: "#7C3AED", task: "#3B82F6", problem: "#EF4444",
          entity: "#F59E0B", preference: "#EC4899", fact: "#6B7280", event: "#14B8A6",
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
