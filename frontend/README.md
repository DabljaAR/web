# DabljaAR Frontend

React SPA for the DabljaAR AI dubbing platform — landing page, authentication, media upload dashboard, job tracking, and result playback.

For full system architecture, see the [root README](../README.md).

## Features

- **Landing page** — hero, problem statement, how-it-works workflow, team section, demo CTA
- **Authentication** — login, register, JWT token management, protected routes
- **Dashboard** — upload video, audio, or text; import from YouTube; choose output type (captions, translation, TTS, full dubbing)
- **Job tracking** — poll backend for pipeline progress and display status updates
- **History** — browse past processing jobs and download results
- **Media library** — manage uploaded original videos
- **Profile** — account settings and subscription info
- **Internationalization** — English and Arabic UI (React context + translation files)
- **PWA** — installable web app with offline-ready service worker

## Stack

| Layer | Technology |
|---|---|
| Framework | React 19 |
| Build tool | Vite 5 |
| Routing | React Router 7 |
| State | Zustand |
| Styling | Tailwind CSS 4 |
| HTTP | Fetch-based API service (`src/services/api.js`) |
| Testing |  Vitest + React Testing Library |
| Linting | ESLint (flat config) + Prettier |

## Project Structure

```text
frontend/
├── public/                  # Static assets, logo, team photos
├── src/
│   ├── components/          # Reusable UI (layout, home, common)
│   ├── pages/               # Route-level views (Dashboard, History, Login, …)
│   ├── features/            # Feature-scoped logic and components
│   ├── hooks/               # Custom React hooks (useTranslation, …)
│   ├── contexts/            # ThemeProvider, LanguageProvider
│   ├── services/            # API client and auth token handling
│   ├── store/               # Zustand global state
│   ├── utils/               # Constants, translations, helpers
│   ├── styles/              # Global and page-specific CSS
│   ├── data/                # Static data (team members)
│   ├── test/                # Test setup and utilities
│   ├── App.jsx              # Router and lazy-loaded page routes
│   └── main.jsx             # React entry point
├── vite.config.ts
├── eslint.config.js
└── package.json
```

## Getting Started

### Preferred (full stack)

From the repository root:

```bash
./start.sh setup
./start.sh run
```

Frontend logs and lifecycle:

```bash
./start.sh logs frontend
./start.sh status
./start.sh stop
```

### Frontend only

**Prerequisites:** Node.js 20+ (24.x recommended), npm

```bash
cd frontend
npm ci
npm run dev
```

The app is available at `http://localhost:5173`. Requires the backend API running at `http://localhost:8000`.

### Production build

```bash
npm run build        # output in dist/
npm run preview      # serve dist/ locally
```

## Scripts

| Command | Description |
|---|---|
| `npm run dev` | Start Vite dev server |
| `npm run build` | Production build |
| `npm run preview` | Preview production build |
| `npm run lint` | ESLint |
| `npm run format` | Prettier |
| `npm test` | Vitest (watch mode) |
| `npm run test:coverage` | Vitest with coverage report |

## Configuration

- **Vite:** `vite.config.ts`
- **Environment variables:** create `.env` in this directory (see `.env.example`)

```env
VITE_API_BASE_URL=http://localhost:8000/api
```

## Docs

- [Root README](../README.md) — product overview and architecture
- [`docs/api.md`](../docs/api.md) — backend API reference
- [`docs/onboarding.md`](../docs/onboarding.md) — full-stack developer setup
- [`AGENTS.md`](AGENTS.md) — conventions for AI agents working in this project
