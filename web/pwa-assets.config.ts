import { defineConfig, minimal2023Preset } from '@vite-pwa/assets-generator/config'

// Fill the padding of maskable and Apple icons with the brand color instead of white.
const brandBackground = { background: '#0E7C74' }

export default defineConfig({
  preset: {
    ...minimal2023Preset,
    maskable: { ...minimal2023Preset.maskable, resizeOptions: brandBackground },
    apple: { ...minimal2023Preset.apple, resizeOptions: brandBackground },
  },
  images: ['public/logo.svg'],
})
