# UI & Frontend Specification

> **Status:** Active / Synchronized with Phase 7 (Frontend Search UI Complete)

## Overview
Specifies the user interface architecture, design tokens, component hierarchy, accessibility requirements, and responsive layout rules for the Private Search Engine web application.

---

## 1. Design Tokens & Color Palette

The interface supports both **Dark Mode** (default) and **Light Mode**, implemented via CSS variables toggled on the `[data-theme]` attribute of `document.documentElement`.

| Token | Dark Theme | Light Theme | Usage |
|---|---|---|---|
| `--primary` | `#3b82f6` (Blue 500) | `#2563eb` (Blue 600) | Brand actions, active page, result links |
| `--primary-hover` | `#2563eb` (Blue 600) | `#1d4ed8` (Blue 700) | Interactive hover states |
| `--primary-light` | `rgba(59, 130, 246, 0.15)` | `rgba(37, 99, 235, 0.1)` | Focus rings, suggestion active row, score tags |
| `--bg` | `#090d16` (Deep Navy Black) | `#f8fafc` (Slate 50) | Main viewport background |
| `--bg-surface` | `#111827` (Gray 900) | `#ffffff` (White) | Header, inputs, dropdowns |
| `--bg-card` | `#162032` (Slate 900) | `#ffffff` (White) | Search result cards, pagination buttons |
| `--bg-card-hover` | `#1c2a42` | `#f1f5f9` (Slate 100) | Card hover background |
| `--text` | `#f9fafb` (Gray 50) | `#0f172a` (Slate 900) | Primary text, headings |
| `--text-secondary` | `#9ca3af` (Gray 400) | `#475569` (Slate 600) | Result descriptions, summaries |
| `--text-muted` | `#6b7280` (Gray 500) | `#64748b` (Slate 500) | Footers, URLs, metadata |
| `--border` | `#1f2937` (Gray 800) | `#e2e8f0` (Slate 200) | Borders, dividers |
| `--success` | `#10b981` (Emerald 500) | `#059669` (Emerald 600) | Ready status, relevance match badge |
| `--error` | `#ef4444` (Red 500) | `#dc2626` (Red 600) | Alert banners, rate limit notices |
| `--highlight-bg` | `rgba(234, 179, 8, 0.25)` | `rgba(253, 224, 71, 0.5)` | Query term background in snippets |
| `--highlight-text` | `#fde047` (Yellow 300) | `#854d0e` (Yellow 900) | Highlighted term text color |

---

## 2. Layout & Responsive Breakpoints

- **Max Container Width**: `900px` centered (`margin: 0 auto`).
- **Breakpoints**:
  - **Desktop / Laptop (> 768px)**: Full multi-column header layout, row search bar with inline action buttons, card padding `1.25rem 1.5rem`.
  - **Mobile ($\le 768\text{px}$)**: Stacked header actions, full-width search input, card padding `1rem`, touch-friendly pagination buttons ($\ge 38\text{px}$ touch targets).

---

## 3. Component Hierarchy & Behaviors

### 3.1 Header (`Header.tsx`)
- **Branding**: Title `🔍 Private Search` with subtitle.
- **System Readiness Indicator**: Live badge showing `● Ready` (green) or `○ Initializing` (amber) with `role="status"` and `aria-live="polite"`.
- **Metrics**: Total indexed document counter (`1,250 docs`).
- **Theme Toggle**: Accessible toggle button switching between Dark and Light mode. Saves preference to `localStorage`.

### 3.2 Search Bar & Autocomplete (`SearchBar.tsx` & `Suggestions.tsx`)
- **Combobox Input**:
  - `role="combobox"`, `aria-autocomplete="list"`, `aria-expanded`, `aria-controls="suggestions-listbox"`.
  - Clear button (`✕`) when input is non-empty.
- **Debounced Suggestions Dropdown**:
  - Automatically fetches suggestions after **300ms** of typing inactivity.
  - Requires a minimum of **2 characters**.
  - Cancels older in-flight requests via `AbortController`.
  - Dropdown uses `role="listbox"` and `role="option"`.
  - Keyboard interactions:
    - `ArrowDown`: Moves highlight down to next suggestion (`aria-activedescendant`).
    - `ArrowUp`: Moves highlight up to previous suggestion.
    - `Enter`: Selects highlighted suggestion and submits search.
    - `Escape`: Closes suggestions dropdown.
  - Outside click listener dismisses dropdown.

### 3.3 Results Display (`ResultsList.tsx` & `SearchResult.tsx`)
- **Loading State**: Accessible spinner with live status announcement: `Searching index for “...”`.
- **Error State**: Banner (`role="alert"`) detailing the failure. If rate limited (HTTP 429), displays countdown badge: `Retry available in Xs`.
- **Empty State**: Friendly prompt offering search tips when no documents match the query.
- **Result Cards**:
  - Domain / Hostname link.
  - Relevance percentage pill badge (e.g. `95% match`).
  - Result title link (opens in new tab with `rel="noopener noreferrer"`).
  - Clean descriptive paragraph.
  - Contextual snippet with query terms highlighted using `<mark className="highlight-term">`. Strictly prohibits `dangerouslySetInnerHTML`.
  - Raw BM25 score.

### 3.4 Pagination (`Pagination.tsx`)
- **Navigation Bar**: Accessible `<nav role="navigation" aria-label="Pagination">`.
- **Windowed Page Controls**: Displays first page, window around current page, ellipsis (`…`), and last page.
- **Active State**: Active button tagged with `aria-current="page"`.
- **Page Transitions**: Automatically executes smooth window scroll to top on page change.

---

## 4. Accessibility (a11y) Conformance

- **WCAG 2.1 AA Compliance**:
  - Contrast ratios for text and background colors exceed 4.5:1.
  - Keyboard focus rings styled with `outline: 2px solid var(--primary)` and `outline-offset: 2px`.
  - No color-alone information: all status badges pair color with text or icons.
  - Screen reader announcements: `aria-live="polite"` on document counts and search metrics.
