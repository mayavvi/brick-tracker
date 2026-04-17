/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        warm: {
          50:  '#fffbf0',
          100: '#fef3e2',
          200: '#fde6c4',
          300: '#fbd49e',
          400: '#f7b267',
          500: '#f49d37',
          600: '#e07b1a',
          700: '#b85d14',
          800: '#8e4712',
          900: '#6b3610',
        }
      }
    }
  },
  plugins: [],
}
