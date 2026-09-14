import type { Config } from "tailwindcss";

export default {
  content: ["./src/**/*.{ts,tsx}"],
  theme: {
    extend: {
      colors: {
        ink: { 900: "#07080d", 800: "#0c0e16", 700: "#12151f", 600: "#1a1e2b" },
        lime: { 400: "#aed44a", 500: "#8fbf24" },
        iris: { 100: "#e6e3f9", 200: "#cbc6f1", 300: "#aca5e6", 400: "#8e86d6", 500: "#6f66b8" },
      },
      fontFamily: { sans: ["var(--font-sans)", "system-ui", "sans-serif"] },
      boxShadow: {
        lift: "0 18px 40px -18px rgba(0,0,0,0.85)",
        glow: "0 6px 18px -8px rgba(0,0,0,0.65)",
        "glow-iris": "0 6px 18px -8px rgba(0,0,0,0.65)",
      },
      keyframes: {
        float: { "0%,100%": { transform: "translateY(0)" }, "50%": { transform: "translateY(-6px)" } },
        shimmer: { "100%": { transform: "translateX(100%)" } },
      },
      animation: { float: "float 6s ease-in-out infinite" },
    },
  },
  plugins: [],
} satisfies Config;
