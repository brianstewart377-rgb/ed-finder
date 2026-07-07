/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{ts,tsx,js,jsx}'],
  theme: {
    extend: {
      // ED:Finder palette — Elite Dangerous orange + metallic silver/grey.
      // Backgrounds use cool charcoal-graphite (with a subtle blue tint so
      // they read as "starlight on metal" rather than flat black).
      colors: {
        // Backgrounds — graphite/gunmetal stack
        bg1:    'hsl(220 12% 6%)',     // page void
        bg2:    'hsl(218 11% 10%)',    // panels
        bg3:    'hsl(216 10% 14%)',    // surfaces, cards
        bg4:    'hsl(215  9% 19%)',    // raised chips / pill bg
        bg5:    'hsl(214  8% 24%)',    // hover surfaces

        // Text
        text:       'hsl(210 14% 92%)',
        'text-dim': 'hsl(215 10% 65%)',

        // Borders & dividers
        border:    'hsl(216 10% 24%)',
        'border-bright': 'hsl(216 10% 38%)',

        // Metallic silver / chrome — primary "secondary" colour
        silver:        '#c8ccd1',          // chrome highlight
        'silver-dk':   '#8a8f96',          // brushed steel
        'silver-2':    '#5e636b',          // gunmetal shadow
        steel:         '#9aa0a8',          // mid-tone brushed steel

        // Elite Dangerous orange — primary brand
        orange:        '#ff7a14',          // ED orange (slightly warmer)
        'orange-lt':   '#ffb074',          // hover/glow
        'orange-dk':   '#cc5400',
        'orange-deep': '#a13e00',          // pressed / dark accent

        // Status / score colours (kept similar but shifted to be brand-coherent)
        green:  '#4ade80',
        gold:   '#fbbf24',
        red:    '#f87171',
        cyan:   '#7dd3fc',
      },
      borderRadius: {
        // Chunky rounded corners — bumped 4-6 px so they're unmistakable
        'chunk-sm': '14px',
        'chunk':    '20px',
        'chunk-lg': '26px',
        'chunk-xl': '34px',
      },
      boxShadow: {
        // Soft glow + crisp ridge — feels like brushed metal under starlight
        'brand':       '0 1px 0 0 hsl(216 10% 38%) inset, 0 0 0 1px hsl(216 10% 22%), 0 8px 24px -12px rgba(0,0,0,0.7)',
        'brand-glow':  '0 0 0 1px rgba(255, 122, 20, 0.35), 0 0 20px -4px rgba(255, 122, 20, 0.45), 0 8px 24px -12px rgba(0,0,0,0.7)',
        'metal':       '0 1px 0 0 rgba(255,255,255,0.06) inset, 0 -1px 0 0 rgba(0,0,0,0.4) inset, 0 6px 22px -10px rgba(0,0,0,0.8)',
        'inner-soft':  'inset 0 1px 2px rgba(0,0,0,0.6)',
      },
      backgroundImage: {
        // Brushed metal gradient — used for navbar / cards backplate.
        'metal':         'linear-gradient(180deg, hsl(216 10% 18%) 0%, hsl(218 11% 12%) 50%, hsl(220 12% 8%) 100%)',
        'metal-active':  'linear-gradient(180deg, hsl(216 10% 22%) 0%, hsl(218 11% 16%) 100%)',
        'orange-grad':   'linear-gradient(135deg, #ff7a14 0%, #ff9c4a 50%, #ff7a14 100%)',
        'silver-grad':   'linear-gradient(135deg, #c8ccd1 0%, #8a8f96 50%, #c8ccd1 100%)',
      },
      fontFamily: {
        ui:   ['Manrope', 'system-ui', 'sans-serif'],
        mono: ['JetBrains Mono', 'ui-monospace', 'monospace'],
        display: ['Orbitron', 'JetBrains Mono', 'monospace'],
      },
    },
  },
  plugins: [],
};
