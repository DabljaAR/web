# AGENTS.md - DabljaAR Frontend

This file provides guidance for AI agents working in the DabljaAR frontend repository.

## Project Overview

DabljaAR is an Arabic dubbing/localization platform. The frontend is a React 19 application using Vite, TypeScript, Zustand for state management, and React Router for navigation.

## Tech Stack

| Layer | Technology |
|-------|------------|
| Framework | React 19 |
| Build Tool | Vite |
| Language | TypeScript |
| State Management | Zustand |
| Routing | React Router 7 |
| Styling | Tailwind CSS 4 |
| Testing | Vitest + React Testing Library |
| Linting | ESLint (flat config) |
| HTTP Client | Axios (custom wrapper) |

---

## Commands

### Development
```bash
npm run dev          # Start dev server
npm run preview      # Preview production build
```

### Building
```bash
npm run build        # Type-check and build for production
```

### Linting
```bash
npm run lint         # Run ESLint on all files
```

### Testing
```bash
npm test             # Run all tests in watch mode
npm test -- --run    # Run all tests once (CI mode)
npm run test:ui      # Run tests with Vitest UI
npm run test:coverage # Run tests with coverage report

# Single test file
npm test -- src/components/common/Button/Button.test.jsx

# Single test by name pattern
npm test -t "renders correctly"

# Run tests matching a pattern
npm test -- --grep "Button"
```

---

## Project Structure

```
frontend/
├── src/
│   ├── components/       # Reusable UI components
│   │   ├── common/       # Button, Input, etc.
│   │   ├── layout/       # Navbar, Footer
│   │   ├── home/         # Home page sections
│   │   ├── dashboard/   # Dashboard components
│   │   └── profile/      # Profile components
│   ├── pages/           # Route pages
│   ├── features/        # Feature-specific code (dashboard)
│   ├── hooks/           # Custom hooks (useAuth, useFetch, etc.)
│   ├── contexts/        # React contexts (Theme, Language)
│   ├── services/        # API services (api.js, authService.js)
│   ├── store/           # Zustand stores
│   ├── utils/           # Utility functions
│   ├── styles/          # Global styles
│   └── test/            # Test utilities and setup
├── public/              # Static assets
├── index.html           # Entry HTML
└── vite.config.ts       # Vite + Vitest config
```

---

## Code Style Guidelines

### Imports

Order imports groups (separate with blank lines):
1. React/Node built-ins
2. Third-party packages (react, react-router-dom, etc.)
3. Local imports (relative paths)

```jsx
import { useState, useEffect } from 'react';
import { useNavigate } from 'react-router-dom';
import axios from 'axios';

import Button from '../components/common/Button/Button';
import { useAuth } from '../../hooks/useAuth';
import { API_ENDPOINTS } from '../../utils/constants';
```

### File Naming

- **Components**: `PascalCase` - `Button.jsx`, `Navbar.jsx`
- **Hooks**: `camelCase` with `use` prefix - `useAuth.js`, `useFetch.js`
- **Services**: `camelCase` - `api.js`, `authService.js`
- **Utils**: `camelCase` - `helpers.js`, `validation.js`
- **Constants**: `camelCase` - `constants.js`
- **Types**: `PascalCase` - `types.ts` (co-located with component)
- **Tests**: Match component name + `.test.jsx` - `Button.test.jsx`

### Component Structure

```jsx
import { useState, useEffect } from 'react';
import PropTypes from 'prop-types';

function MyComponent({ title, onSubmit }) {
  const [state, setState] = useState(null);

  useEffect(() => {
    // effect logic
  }, []);

  const handleClick = () => {
    // handler logic
  };

  return (
    <div className="...">
      <h1>{title}</h1>
      <button onClick={handleClick}>Click</button>
    </div>
  );
}

MyComponent.propTypes = {
  title: PropTypes.string.isRequired,
  onSubmit: PropTypes.func,
};

MyComponent.defaultProps = {
  onSubmit: () => {},
};

export default MyComponent;
```

### TypeScript Usage

This project uses **JSX with loose typing** (like older React projects). TypeScript is used via `tsconfig.json` but components are primarily `.jsx` files. When adding types:

```jsx
// Prefer explicit types for props
function Button({ variant = 'primary', disabled = false, children, onClick }) {
  // ...
}

// Use JSDoc for complex functions if needed
/**
 * @param {string} endpoint - API endpoint
 * @param {object} options - Fetch options
 * @returns {Promise<object>}
 */
```

### Zustand Store Pattern

```jsx
// store/useAuthStore.js
import { create } from 'zustand';

const useAuthStore = create((set) => ({
  user: null,
  token: null,
  isAuthenticated: false,
  
  login: (user, token) => set({ user, token, isAuthenticated: true }),
  logout: () => set({ user: null, token: null, isAuthenticated: false }),
}));

export default useAuthStore;
```

### Error Handling

```jsx
// In services
try {
  const response = await axios.get(url);
  return response.data;
} catch (error) {
  if (error.response?.status === 401) {
    // Handle unauthorized
  }
  throw error;
}

// In components
const { data, error, loading } = useFetch(endpoint);

if (error) {
  return <div>Error: {error.message}</div>;
}
```

### Tailwind CSS

- Use Tailwind utility classes directly in JSX
- Avoid inline styles
- Use semantic class names for complex components

```jsx
<div className="flex items-center justify-between p-4 bg-white rounded-lg shadow">
  <h2 className="text-xl font-semibold text-gray-800">Title</h2>
</div>
```

---

## Testing Guidelines

### Test File Location

Co-locate tests with components:
- `src/components/common/Button/Button.jsx`
- `src/components/common/Button/Button.test.jsx`

### Test Patterns

```jsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Button from './Button';

describe('Button', () => {
  it('renders with children', () => {
    render(<Button>Click me</Button>);
    expect(screen.getByText('Click me')).toBeInTheDocument();
  });

  it('handles click events', async () => {
    const user = userEvent.setup();
    const onClick = vi.fn();
    render(<Button onClick={onClick}>Click</Button>);
    
    await user.click(screen.getByRole('button'));
    expect(onClick).toHaveBeenCalled();
  });
});
```

### Hook Testing

```jsx
import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useCounter } from './useCounter';

describe('useCounter', () => {
  it('increments value', () => {
    const { result } = renderHook(() => useCounter());
    
    act(() => {
      result.current.increment();
    });
    
    expect(result.current.count).toBe(1);
  });
});
```

---

## Testing Checklist

- Test component renders with different props
- Test user interactions (clicks, inputs)
- Test loading and error states
- Test conditional rendering
- Mock external dependencies (API calls, localStorage)
- Use semantic queries (`getByRole`, `getByLabelText`) over `getByTestId`

---

## Common Patterns

### Protected Routes

```jsx
// src/components/common/ProtectedRoute.jsx
import { Navigate } from 'react-router-dom';
import useAuthStore from '../../store/useAuthStore';

function ProtectedRoute({ children }) {
  const { isAuthenticated } = useAuthStore();
  
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }
  
  return children;
}

export default ProtectedRoute;
```

### API Service Pattern

```jsx
// src/services/api.js
import axios from 'axios';

const api = axios.create({
  baseURL: import.meta.env.VITE_API_URL || '/api',
});

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('accessToken');
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

// Add response interceptor for token refresh if needed
export default api;
```

### Custom Hook Pattern

```jsx
// src/hooks/useFetch.js
import { useState, useEffect } from 'react';
import api from '../services/api';

function useFetch(url) {
  const [data, setData] = useState(null);
  const [loading, setLoading] = useState(true);
  const [error, setError] = useState(null);

  useEffect(() => {
    const fetchData = async () => {
      try {
        setLoading(true);
        const response = await api.get(url);
        setData(response.data);
      } catch (err) {
        setError(err);
      } finally {
        setLoading(false);
      }
    };

    fetchData();
  }, [url]);

  return { data, loading, error };
}

export default useFetch;
```

---

## Environment Variables

Create `.env` file in frontend root:
```env
VITE_API_URL=http://localhost:8000
```

---

## Key Files Reference

- **Main Entry**: `src/main.jsx`
- **App Router**: `src/App.jsx`
- **Auth Store**: `src/store/useAuthStore.js`
- **API Client**: `src/services/api.js`
- **Test Setup**: `src/test/setup.js`
- **Test Utils**: `src/test/test-utils.jsx`

---

## ESLint Configuration

The project uses ESLint flat config with:
- `@eslint/js` - Base JavaScript rules
- `typescript-eslint` - TypeScript support
- `eslint-plugin-react-hooks` - React hooks rules
- `eslint-plugin-react-refresh` - HMR-safe patterns

Run `npm run lint` to check for issues.

(End of file)