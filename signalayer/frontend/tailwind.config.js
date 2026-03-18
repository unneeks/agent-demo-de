/** @type {import('tailwindcss').Config} */
export default {
  content: ["./frontend/index.html", "./frontend/src/**/*.{js,jsx}"],
  theme: {
    extend: {
      colors: {
        ink: "#08111f",
        shell: "#0f1728",
        panel: "#13213a",
        line: "#24324d",
        accent: "#65d7c4",
        warn: "#f6b85f",
        danger: "#f7827f",
        text: "#e5edf9",
        mute: "#8fa0ba"
      },
      boxShadow: {
        glow: "0 20px 60px rgba(7, 15, 28, 0.35)"
      },
      fontFamily: {
        sans: ["IBM Plex Sans", "system-ui", "sans-serif"],
        display: ["Space Grotesk", "IBM Plex Sans", "sans-serif"]
      }
    }
  },
  plugins: []
};
