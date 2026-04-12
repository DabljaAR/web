# DabljaAR Brand Kit — v1.0

> Complete brand identity guidelines for the DabljaAR AI Video Dubbing Platform.

---

## 1. Brand Identity

**DabljaAR** is an AI-powered video dubbing and translation platform.  
The name combines **دبلجة** (*dubbing* in Arabic) with **AR** (Arabic) — emphasizing intelligent, culturally-aware media localization.

**Brand voice:** Precise · Trustworthy · Modern · Accessible

---

## 2. Logo

All logo files live in [`frontend/src/assets/brand/`](../frontend/src/assets/brand/).

| File | Usage |
|------|-------|
| `logo-primary.svg` | Default — light backgrounds, web, presentations |
| `logo-dark.svg` | Dark/navy backgrounds, hero sections |
| `logo-monochrome.svg` | Single-color contexts (print, embossing, stamps) |
| `logo-icon.svg` | Favicon, app icon, avatar, small placements |

### Construction

The icon mark is a **gradient rounded square** (corner radius 14 px) containing five vertical waveform bars in an arch configuration. The arch silhouette references:

- An **audio waveform** → the AI audio pipeline (STT → NMT → TTS)
- The letter **D** → Dablja / دبلجة

An **amber dot** at the icon's bottom-right corner represents the **AR** (Arabic) identity anchor.

### Clear space

Maintain a minimum clear space of **1× the icon mark height** on all sides of the full logo.

### Minimum size

| Format | Minimum |
|--------|---------|
| Digital (px) | 120 px wide (full logo) / 32 px (icon only) |
| Print (mm) | 35 mm wide (full logo) / 10 mm (icon only) |

### What NOT to do

- Do not recolor the waveform bars independently
- Do not stretch or distort the logo
- Do not place the primary logo on busy photographic backgrounds (use `logo-dark.svg` on dark overlays instead)
- Do not add drop shadows or outlines

---

## 3. Color Palette

Reference sheet: [`frontend/src/assets/brand/color-palette.svg`](../frontend/src/assets/brand/color-palette.svg)

### Primary Colors

| Token | Hex | Tailwind class | Usage |
|-------|-----|----------------|-------|
| Brand Primary | `#4338CA` | `brand-primary` | CTAs, links, active states |
| Brand Secondary | `#7C3AED` | `brand-secondary` | Gradient end, hover states |
| AR Accent | `#D97706` | `brand-accent` | "AR" wordmark, highlights, badges |
| Deep Dark | `#1E1B4B` | `brand-dark` | Headings, navbar, dark surfaces |
| Soft Tint | `#E0E7FF` | `brand-tint` | Backgrounds, hover fills, chips |

### Gradient

```css
background: linear-gradient(135deg, #4338CA 0%, #7C3AED 100%);
```

Tailwind: `bg-brand-gradient` or `className="brand-gradient"`

### Semantic Colors

| State | Hex | Tailwind |
|-------|-----|---------|
| Success | `#059669` | `success` |
| Warning | `#D97706` | `warning` |
| Error | `#DC2626` | `danger` |
| Info | `#0891B2` | `info` |

### Neutrals

| Role | Hex | Notes |
|------|-----|-------|
| Body text | `#475569` | Slate 600 |
| Muted text | `#94A3B8` | Slate 400 |
| Border | `#E2E8F0` | Slate 200 |
| Background | `#F1F5F9` | Slate 100 |
| Surface | `#FFFFFF` | Cards, modals |

---

## 4. Typography

### Font Stack

| Role | Family | Weight | Import |
|------|--------|--------|--------|
| **Display / Headings** | Cairo | 700 (Bold), 800 (ExtraBold) | Google Fonts |
| **Body** | Inter | 400 (Regular), 500 (Medium), 600 (SemiBold) | Google Fonts |
| **Code / Timestamps / IDs** | JetBrains Mono | 400, 500 | Google Fonts |

**Cairo** supports both Arabic and Latin script — use it for all bilingual content.

### Scale

| Token | Size | Weight | Leading | Usage |
|-------|------|--------|---------|-------|
| Display | 48 px | 800 | 1.1 | Hero headlines |
| H1 | 36 px | 700 | 1.2 | Page titles |
| H2 | 28 px | 700 | 1.25 | Section headings |
| H3 | 22 px | 600 | 1.3 | Card headings |
| Body LG | 18 px | 400 | 1.6 | Lead paragraphs |
| Body | 16 px | 400 | 1.6 | Default text |
| Body SM | 14 px | 400 | 1.5 | Supporting text |
| Caption | 12 px | 500 | 1.4 | Labels, metadata |
| Overline | 11 px | 600 + 2px tracking | 1 | Section labels (uppercase) |

### Arabic (RTL)

All Arabic text uses **Cairo**. Set `direction: rtl` via the `.rtl` utility class or `lang="ar"` attribute (handled in `index.css`).

---

## 5. UI Icon Set

All icons: [`frontend/src/assets/brand/icons/`](../frontend/src/assets/brand/icons/)

| File | Description | Platform context |
|------|-------------|-----------------|
| `icon-waveform.svg` | Audio waveform bars | STT (Speech-to-Text) pipeline stage |
| `icon-translate.svg` | Globe with meridians | NMT translation stage |
| `icon-speaker.svg` | Speaker with sound waves | TTS (Text-to-Speech) stage |
| `icon-upload.svg` | Upload arrow | Video ingestion |
| `icon-video.svg` | Video camera | Video file / original media |
| `icon-dashboard.svg` | 2×2 tile grid | Dashboard navigation |
| `icon-history.svg` | Clock with back-arrow | Job history / activity log |
| `icon-profile.svg` | User silhouette | Account / profile |
| `icon-check-circle.svg` | Checkmark in circle | Completed job state |
| `icon-processing.svg` | Spinner arc | In-progress job state |

### Icon Spec

- **ViewBox:** `0 0 24 24`
- **Stroke:** `currentColor`, `stroke-width="1.75"`, `stroke-linecap="round"`, `stroke-linejoin="round"`
- **Fill:** `none` (outline style — color via CSS)
- **Animation:** Add `.icon-spin` class to `icon-processing.svg` for continuous rotation

### Usage in React/JSX

```jsx
import { ReactComponent as WaveformIcon } from '@/assets/brand/icons/icon-waveform.svg';

// Inline with Tailwind
<WaveformIcon className="w-6 h-6 text-brand-primary" />

// As <img> (no color control)
<img src="/assets/brand/icons/icon-waveform.svg" width="24" height="24" alt="STT" />
```

---

## 6. Presentation Slide Guidelines

| Element | Spec |
|---------|------|
| Title slide background | Brand gradient (`#4338CA → #7C3AED`) |
| Section dividers | Amber accent bar (`#D97706`, 4 px height) |
| Body slide background | White `#FFFFFF` or Slate 100 `#F1F5F9` |
| Heading color | Deep Dark `#1E1B4B` |
| Accent / highlight | Amber `#D97706` |
| Chart palette | Primary → Secondary → Accent → Info → Success |
| Logo placement | Bottom-right, `logo-dark.svg` on gradient slides |

---

## 7. Token Reference (Tailwind)

```js
// tailwind.config.js tokens already configured:

bg-brand-primary      // #4338CA
bg-brand-secondary    // #7C3AED
bg-brand-accent       // #D97706
bg-brand-dark         // #1E1B4B
bg-brand-tint         // #E0E7FF
bg-brand-gradient     // 135deg indigo→violet
text-brand-primary
text-brand-accent
border-brand-tint
font-display          // Cairo
font-body             // Inter
font-mono             // JetBrains Mono
```

---

*DabljaAR Brand Kit · v1.0 · April 2026*
