/** @type {import('tailwindcss').Config} */
export default {
  content: ['./index.html', './src/**/*.{vue,js,ts,jsx,tsx}'],
  theme: {
    extend: {
      colors: {
        primary: {
          50: '#eff6ff',
          100: '#dbeafe',
          200: '#bfdbfe',
          300: '#93c5fd',
          400: '#60a5fa',
          500: '#3b82f6',
          600: '#2563eb',
          700: '#1d4ed8',
          800: '#1e40af',
          900: '#1e3a8a'
        },
        brand: {
          50: '#eef4fe',
          100: '#d9e7ff',
          200: '#b9d1ff',
          500: '#2b4ee6',
          600: '#2440c5',
          700: '#1c319f',
          800: '#15266f',
          900: '#0e1b4f'
        },
        ink: {
          50: '#f9fafb',
          100: '#f3f4f6',
          200: '#e5e7eb',
          300: '#d1d5db',
          400: '#9ca3af',
          500: '#6b7280',
          600: '#4b5563',
          700: '#374151',
          800: '#1f2937',
          900: '#111827',
          950: '#030712'
        },
        line: {
          DEFAULT: 'rgb(var(--sl-border-default-rgb) / <alpha-value>)',
          soft: 'rgb(var(--sl-border-soft-rgb) / <alpha-value>)',
          strong: 'rgb(var(--sl-border-strong-rgb) / <alpha-value>)'
        },
        surface: {
          DEFAULT: 'rgb(var(--sl-bg-surface-rgb) / <alpha-value>)',
          sunken: 'rgb(var(--sl-bg-canvas-rgb) / <alpha-value>)',
          raised: 'rgb(var(--sl-bg-raised-rgb) / <alpha-value>)',
          hover: 'rgb(var(--sl-bg-hover-rgb) / <alpha-value>)',
          selected: 'rgb(var(--sl-bg-selected-rgb) / <alpha-value>)'
        },
        success: {
          DEFAULT: '#1f9d6b',
          50: '#e8f7f0',
          100: '#cfeedd',
          600: '#16855a',
          700: '#106a49'
        },
        warning: {
          DEFAULT: '#c98a17',
          50: '#fff6e3',
          100: '#fbe9bc',
          600: '#ad7210',
          700: '#8d5d0c'
        },
        danger: {
          DEFAULT: '#d2533f',
          50: '#fef0ec',
          100: '#f7d8d1',
          600: '#b74230',
          700: '#943427'
        },
        gray: {
          50: '#f9fafb',
          100: '#f3f4f6',
          200: '#e5e7eb',
          300: '#d1d5db',
          400: '#9ca3af',
          500: '#6b7280',
          600: '#4b5563',
          700: '#374151',
          800: '#1f2937',
          900: '#111827'
        }
      },
      textColor: {
        theme: {
          DEFAULT: 'rgb(var(--sl-text-primary-rgb) / <alpha-value>)',
          secondary: 'rgb(var(--sl-text-secondary-rgb) / <alpha-value>)',
          muted: 'rgb(var(--sl-text-muted-rgb) / <alpha-value>)',
          subtle: 'rgb(var(--sl-text-subtle-rgb) / <alpha-value>)'
        }
      },
      fontFamily: {
        sans: ['Inter', 'Noto Sans SC', 'system-ui', 'sans-serif']
      },
      borderRadius: {
        DEFAULT: '12px',
        sm: '8px',
        md: '10px',
        lg: '12px',
        xl: '16px',
        '2xl': '20px'
      },
      boxShadow: {
        soft: '0 1px 3px rgba(0, 0, 0, 0.05)',
        'soft-md': '0 4px 12px rgba(0, 0, 0, 0.08)',
        'soft-lg': '0 10px 24px rgba(0, 0, 0, 0.10)'
      },
      container: {
        center: true,
        padding: '1rem',
        screens: {
          sm: '640px',
          md: '768px',
          lg: '1024px',
          xl: '1280px',
          '2xl': '1400px'
        }
      }
    }
  },
  plugins: []
}
