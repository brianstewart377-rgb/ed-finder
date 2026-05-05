/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx}'],
  theme: {
    extend: {
      // Mirror the vanilla app's CSS variables so the v2 visual identity
      // doesn't drift while we port. Once the migration is feature-complete
      // we can replace these with proper design tokens.
      colors: {
        bg1:    'hsl(225 30% 5%)',
        bg2:    'hsl(225 25% 8%)',
        bg3:    'hsl(225 20% 12%)',
        bg4:    'hsl(225 18% 16%)',
        text:   'hsl(220 30% 92%)',
        'text-dim': 'hsl(220 15% 60%)',
        border: 'hsl(225 20% 22%)',
        orange:    '#ff6a00',
        'orange-dk': '#cc5400',
        green:  '#3ddc84',
        gold:   '#facc15',
        red:    '#ef4444',
        cyan:   '#22d3ee',
      },
      fontFamily: {
        ui:   ['system-ui', 'sans-serif'],
        mono: ['Orbitron', 'JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};
