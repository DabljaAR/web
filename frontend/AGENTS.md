# AGENTS.md - DabljaAR Frontend

Guidance for AI agents working in the frontend project.

## Project Overview

DabljaAR frontend is a React 19 SPA built with Vite, Zustand, React Router, and Tailwind CSS.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | React 19 |
| Build Tool | Vite 5 |
| Language | JavaScript (JSX) + TypeScript tooling |
| State Management | Zustand |
| Routing | React Router 7 |
| Styling | Tailwind CSS 4 |
| Testing | Vitest + React Testing Library |
| Linting | ESLint (flat config) |
| HTTP Client | Fetch-based API service (`src/services/api.js`) |

## Commands

```bash
npm run dev
npm run build
npm run lint
npm test
npm test -- --run
npm run test:coverage
```

## Structure

```text
frontend/
├── src/
│   ├── components/
│   ├── pages/
│   ├── features/
│   ├── hooks/
│   ├── contexts/
│   ├── services/
│   ├── store/
│   ├── utils/
│   ├── styles/
│   └── test/
├── public/
└── vite.config.ts
```

## Conventions

- Prefer functional components and hooks.
- Keep feature logic close to feature folders.
- Use `src/services/api.js` for HTTP calls and auth token handling.
- Keep tests near components/hooks when possible.

## Environment Variables

```env
VITE_API_BASE_URL=http://localhost:8000/api
```

## Key Files

- `src/App.jsx`
- `src/main.jsx`
- `src/services/api.js`
- `src/store/store.js`
- `src/test/setup.js`
