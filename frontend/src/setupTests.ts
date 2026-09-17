import '@testing-library/jest-dom'

// Mock window.matchMedia if not available in JSDOM
if (typeof window !== 'undefined' && !window.matchMedia) {
  Object.defineProperty(window, 'matchMedia', {
    writable: true,
    value: (query: string) => ({
      matches: false,
      media: query,
      onchange: null,
      addListener: () => {},
      removeListener: () => {},
      addEventListener: () => {},
      removeEventListener: () => {},
      dispatchEvent: () => false,
    }),
  })
}

// Mock window.scrollTo in JSDOM
if (typeof window !== 'undefined') {
  window.scrollTo = () => {}
}
