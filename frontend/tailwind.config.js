/** @type {import('tailwindcss').Config} */
module.exports = {
    content: [
        "./src/pages/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/components/**/*.{js,ts,jsx,tsx,mdx}",
        "./src/app/**/*.{js,ts,jsx,tsx,mdx}",
    ],
    theme: {
        extend: {
            colors: {
                background: "#0b0f1a",
                surface: "rgba(255, 255, 255, 0.03)",
                surfaceHover: "rgba(255, 255, 255, 0.06)",
                border: "rgba(255, 255, 255, 0.08)",
                primary: "#6366f1", // Indigo
                secondary: "#06b6d4", // Cyan
                success: "#22c55e", // Green
                warning: "#f59e0b", // Amber
                danger: "#f43f5e", // Rose
            },
            backgroundImage: {
                'gradient-radial': 'radial-gradient(var(--tw-gradient-stops))',
                'hero-gradient': 'linear-gradient(to right, #6366f1, #06b6d4, #22c55e)',
            },
            fontFamily: {
                sans: ['Inter', 'sans-serif'],
            },
            animation: {
                'pulse-slow': 'pulse 3s cubic-bezier(0.4, 0, 0.6, 1) infinite',
                'float': 'float 6s ease-in-out infinite',
            },
            keyframes: {
                float: {
                    '0%, 100%': { transform: 'translateY(0)' },
                    '50%': { transform: 'translateY(-10px)' },
                }
            }
        },
    },
    plugins: [],
}
