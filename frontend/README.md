# Private Search Engine - Frontend

Modern, privacy-first search web application built with **React 18**, **Vite 5**, and **TypeScript** in strict mode.

---

## Features

- **React 18 & TypeScript**: Strongly typed components, hooks, and API interfaces matching Phase 6 backend models.
- **URL Synchronization**: Search query and pagination state shareable through URL query parameters (e.g. `/?q=python&page=2`).
- **Debounced Autocomplete**: 300ms debounce with minimum 2 characters, keyboard navigation (Arrow Up/Down), Enter selection, Escape closing, and outside-click detection.
- **Request Cancellation**: Active `AbortController` cancellation for stale in-flight search and suggestion requests.
- **Safe Snippet Highlighting**: Contextual snippet keyword highlighting using React virtual DOM elements (`<mark>`), guaranteeing zero use of `dangerouslySetInnerHTML`.
- **Accessible UI**: ARIA combobox, listbox, polite status announcements, and keyboard navigable controls.
- **Theme Support**: Dark and Light theme toggle with system preference fallback and `localStorage` persistence.
- **Error & Edge States**: Gracefully formats 422 (invalid query), 429 (rate limit with `Retry-After`), 500 (server error), 503 (service unavailable), and network dropouts.
- **Vite Proxy**: Automatically proxies `/api` requests to `http://localhost:8000` during local development.

---

## Development & Build Commands

```bash
# Install dependencies
npm install

# Start local dev server (port 3000)
npm run dev

# Run TypeScript type check
npm run type-check

# Run Vitest test suite
npm test

# Build production bundle
npm run build

# Preview production build
npm run preview
```

