/** @type {import('tailwindcss').Config} */
module.exports = {
  content: ["./templates/**/*.html", "./static/js/**/*.js"],
  theme: {
    extend: {
      colors: {
        warm: {
          50:  '#F4FBF8',
          100: '#DDF3EA',
          200: '#B9E4D6',
          300: '#86CFB9',
          400: '#4CB295',
          500: '#2E9279',
          600: '#247662',
          700: '#205F51',
          800: '#184A40',
          900: '#123832',
        },
        neon: {
          50:  '#FFF4F8',
          100: '#FFE3EE',
          200: '#FCC9DC',
          300: '#F4A9C7',
          400: '#E986B0',
          500: '#DB5D91',
          600: '#C2497C',
          700: '#A73568',
          800: '#842B55',
          900: '#632240',
        }
      }
    }
  },
  plugins: [],
}
