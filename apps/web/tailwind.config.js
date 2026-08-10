/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: '#14b78c',
        primarydark: '#0e614c',
        secondary: '#f5f5f5',
        accent: '#14b78c',
        background: '#ffffff',
        text: '#000000',
        mint: {
          50: '#ecfdf7',
          100: '#d1faec',
          200: '#a6f4dc',
          300: '#6ee8c5',
          400: '#35d6a9',
          500: '#14b78c',
          600: '#0c9973',
          700: '#0c7a5e',
          800: '#0e614c',
          900: '#0d4f3f',
        },
      },
    },
  },
  plugins: [],
};
