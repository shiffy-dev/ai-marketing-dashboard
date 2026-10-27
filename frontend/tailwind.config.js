/**
 * Design tokens extracted from https://ecomma.co/ (computed styles + :root CSS variables).
 * The palette, radii, shadows and type scale REPLACE Tailwind's defaults so only these tokens can be used.
 */
/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{js,jsx}'],
  theme: {
    colors: {
      transparent: 'transparent',
      current: 'currentColor',
      white: '#ffffff',
      navy: '#0f172a', // --c-primary: headlines on light, dark band background
      ink: '#111827', // --c-ink
      body: '#1f2937', // --c-text
      muted: '#4b5563', // --c-text-muted
      soft: '#6b7280', // --c-text-soft
      slate: '#94a3b8', // secondary text on dark
      rule: '#e5e7eb', // --c-rule
      'rule-soft': '#f3f4f6', // --rule2
      brand: { DEFAULT: '#073877', deep: '#0a4a9a', tint: 'rgba(7, 56, 119, 0.1)' }, // --c-brand
      cyan: { DEFAULT: '#57cafb', soft: '#d6f0fb', tint: '#ecf8fe' }, // --c-accent
      page: '#ffffff',
      'page-soft': '#f6f9fc', // --c-bg-soft
      green: '#17a673', // --green
      amber: '#b45309',
      'amber-tint': '#fef3c7',
      red: '#b91c1c',
      'red-tint': '#fee2e2',
      'green-tint': '#dcfce7',
    },
    fontFamily: {
      sans: ['Inter', 'system-ui', '-apple-system', '"Segoe UI"', 'sans-serif'],
      serif: ['"Playfair Display"', 'Georgia', 'serif'],
    },
    fontSize: {
      eyebrow: ['12px', { lineHeight: '1', letterSpacing: '0.16em', fontWeight: '700' }],
      xs: ['13px', { lineHeight: '20px' }],
      sm: ['14px', { lineHeight: '22px' }],
      card: ['15px', { lineHeight: '24px' }],
      base: ['16px', { lineHeight: '25.6px' }],
      lede: ['17px', { lineHeight: '27.2px' }],
      h3: ['22px', { lineHeight: '1.12', letterSpacing: '-0.01em', fontWeight: '600' }],
      band: ['clamp(23px, 2.15vw, 28px)', { lineHeight: '1.15', letterSpacing: '-0.01em', fontWeight: '600' }],
      h2: ['clamp(28px, 2.8vw, 34px)', { lineHeight: '1.12', letterSpacing: '-0.01em', fontWeight: '600' }],
      h1: ['clamp(34px, 3.6vw, 52px)', { lineHeight: '1.12', letterSpacing: '-0.01em', fontWeight: '600' }],
      stat: ['clamp(36px, 3.6vw, 52px)', { lineHeight: '1', fontWeight: '800' }],
    },
    borderRadius: {
      none: '0',
      sm: '4px',
      md: '8px', // buttons
      lg: '11px',
      card: '14px', // .hp-card
      full: '999px',
    },
    boxShadow: {
      none: 'none',
      card: '0 1px 0 0 rgba(15, 23, 42, 0.02), 0 4px 24px -12px rgba(7, 56, 119, 0.08)',
      lift: '0 26px 70px -62px rgba(7, 56, 119, 0.7)',
      drawer: '0 24px 64px -42px rgba(7, 56, 119, 0.7)',
      button: 'inset 0 1px 0 0 rgba(255, 255, 255, 0.16), 0 10px 24px -10px rgba(7, 56, 119, 0.65)',
    },
    extend: {
      spacing: {
        gutter: '32px', // --gutter
        section: '96px', // --section-y
        rule: '24px', // eyebrow rule width
      },
      maxWidth: { page: '1200px', lede: '34em' },
      height: { hairline: '2px' },
    },
  },
  plugins: [],
}
