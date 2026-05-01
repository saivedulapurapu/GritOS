/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./pages/**/*.{js,jsx,mdx}",
        "./components/**/*.{js,jsx,mdx}",
        "./app/**/*.{js,jsx,mdx}",
        "./styles/**/*.css",
    ],
    theme: {
        extend: {
            colors: {
                background: 'var(--background)',
                foreground: 'var(--foreground)',
            },
        },
    },
    plugins: [],
};
