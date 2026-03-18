export default {
  prefix: "sl-",
  content: ["./extension/src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: {
          950: "#020617",
          900: "#0f172a",
          800: "#172033",
          700: "#243047"
        },
        accent: {
          500: "#38bdf8",
          400: "#67e8f9",
          300: "#a5f3fc"
        },
        success: "#34d399",
        warning: "#fbbf24",
        danger: "#fb7185"
      },
      boxShadow: {
        signal: "0 20px 45px rgba(2, 6, 23, 0.45)"
      },
      fontFamily: {
        sans: ["ui-sans-serif", "system-ui", "sans-serif"]
      }
    }
  },
  plugins: []
};
