/** Tailwind config for the static web app. Build: npm run build:css */
module.exports = {
    content: ['./ui/index.html', './ui/app.js'],
    theme: {
        extend: {
            colors: {
                'nyaya-blue': '#1A237E',
                'nyaya-blue-light': '#3949AB',
                'justice-gold': '#C5A059',
            },
            fontFamily: {
                sans: ['Inter', 'system-ui', '-apple-system', 'Segoe UI', 'Roboto', 'Noto Sans', 'sans-serif'],
            },
        },
    },
};
