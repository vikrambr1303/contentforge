/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,jsx}"],
  theme: {
    extend: {
      fontFamily: {
        sans: ["Inter", "system-ui", "sans-serif"],
      },
      colors: {
        forge: {
          950: "#0c0f14",
          900: "#12161e",
          800: "#1a2030",
          700: "#243044",
          600: "#2e3d52",
          500: "#3d4f66",
          accent: "#38bdf8",
        },
      },
    },
  },
  plugins: [],
};
