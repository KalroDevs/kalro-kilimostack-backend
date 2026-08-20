/** @type {import('tailwindcss').Config} */
export default {
  content: ["./index.html", "./src/**/*.{js,ts,jsx,tsx}"],
  theme: {
    extend: {
      colors: {
        canvas: "#EDEFEA",
        canvas2: "#E4E7DE",
        ink: "#16211B",
        herbarium: {
          DEFAULT: "#23492E",
          light: "#2F5C3B",
          dark: "#152E1D",
        },
        moss: {
          DEFAULT: "#6B8F71",
          light: "#8CA98F",
          dark: "#4E6E53",
        },
        ochre: {
          DEFAULT: "#C08829",
          light: "#DCA84F",
          dark: "#96691C",
        },
        rust: {
          DEFAULT: "#9C3B2E",
          light: "#BC5744",
          dark: "#7A2C22",
        },
        wire: "#CBD1C4",
        paper: "#F6F5EF",
      },
      fontFamily: {
        display: ["Fraunces", "ui-serif", "Georgia", "serif"],
        sans: ["Inter", "ui-sans-serif", "system-ui", "sans-serif"],
        mono: ["'IBM Plex Mono'", "ui-monospace", "SFMono-Regular", "monospace"],
      },
      boxShadow: {
        card: "0 1px 2px rgba(22, 33, 27, 0.06), 0 1px 0 rgba(22, 33, 27, 0.04)",
        stamp: "0 0 0 1px rgba(22, 33, 27, 0.08)",
      },
      backgroundImage: {
        grain: "radial-gradient(circle at 1px 1px, rgba(22,33,27,0.05) 1px, transparent 0)",
      },
    },
  },
  plugins: [],
};
