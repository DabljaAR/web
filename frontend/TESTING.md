# Frontend Testing Documentation

## Overview

This project includes comprehensive unit tests for the frontend application using Vitest and React Testing Library.

## Setup

### Installation

The testing dependencies are already included in `package.json`. To install them:

```bash
cd frontend
npm install
```

### Running Tests

```bash
# Run tests in watch mode (default)
npm test

# Run tests with UI
npm run test:ui

# Run tests with coverage report
npm run test:coverage
```

## Test Coverage

### Components

#### Common Components
- ✅ **Button** (`src/components/common/Button/Button.test.jsx`)
  - Renders with children
  - Handles onClick events
  - Applies variant styles (primary, secondary, danger)
  - Supports custom className
  - Passes through additional props

- ✅ **Input** (`src/components/common/Input/Input.test.jsx`)
  - Renders with/without label
  - Displays placeholder text
  - Handles onChange events
  - Shows error messages
  - Applies error styling
  - Supports different input types

- ✅ **ProtectedRoute** (`src/components/common/ProtectedRoute.test.jsx`)
  - Renders children when authenticated
  - Shows loading state
  - Redirects when not authenticated
  - Handles authentication state changes

- ✅ **PublicRoute** (`src/components/common/PublicRoute.test.jsx`)
  - Renders children when not authenticated
  - Shows loading state
  - Redirects when authenticated
  - Handles authentication state changes

#### Layout Components
- ✅ **Navbar** (`src/components/layout/Navbar.test.jsx`)
  - Renders with logo
  - Shows login button when not authenticated
  - Shows user menu when authenticated
  - Handles theme toggle
  - Handles language toggle
  - Handles logout

- ✅ **Footer** (`src/components/layout/Footer.test.jsx`)
  - Renders footer sections
  - Displays translation keys
  - Handles scroll to section

#### Feature Components
- ✅ **DashboardCard** (`src/features/dashboard/components/DashboardCard.test.jsx`)
  - Renders with title and value
  - Displays icon when provided
  - Applies custom className

### Hooks

- ✅ **useAuth** (`src/hooks/useAuth.test.js`)
  - Returns null when no token exists
  - Loads user from localStorage/sessionStorage
  - Login stores tokens correctly
  - Logout clears all tokens
  - Handles invalid user data
  - Listens to storage changes

- ✅ **useFetch** (`src/hooks/useFetch.test.js`)
  - Returns loading state initially
  - Fetches data successfully
  - Handles fetch errors
  - Handles HTTP errors
  - Refetches when URL changes

- ✅ **useTranslation** (`src/hooks/useTranslation.test.js`)
  - Returns translation function
  - Translates simple and nested keys
  - Returns key when translation missing
  - Uses correct language from context

- ✅ **useDashboard** (`src/features/dashboard/hooks/useDashboard.test.js`)
  - Returns stats when data available
  - Returns loading state
  - Returns error state
  - Updates stats when data changes

### Services

- ✅ **api** (`src/services/api.test.js`)
  - GET requests with/without auth
  - POST requests with token refresh
  - PUT requests
  - DELETE requests
  - Error handling
  - Token management

- ✅ **authService** (`src/services/authService.test.js`)
  - Login with credentials
  - Register with user data
  - Logout
  - Get current user
  - Refresh token

- ✅ **dashboardService** (`src/features/dashboard/services/dashboardService.test.js`)
  - Get stats
  - Get recent activity
  - Error handling

### Utilities

- ✅ **helpers** (`src/utils/helpers.test.js`)
  - formatDate
  - debounce
  - capitalize
  - generateId
  - isValidEmail

- ✅ **validation** (`src/features/auth/utils/validation.test.js`)
  - validateEmail
  - validatePassword
  - validateLoginForm

- ✅ **formatStats** (`src/features/dashboard/utils/formatStats.test.js`)
  - formatStats
  - formatCurrency

- ✅ **constants** (`src/utils/constants.test.js`)
  - API_ENDPOINTS
  - APP_NAME, APP_VERSION
  - STORAGE_KEYS
  - ROUTES

### Contexts

- ✅ **LanguageContext** (`src/contexts/LanguageContext.test.jsx`)
  - Provides default language
  - Loads from localStorage
  - Toggles language
  - Sets document attributes
  - Error handling

- ✅ **ThemeContext** (`src/contexts/ThemeContext.test.jsx`)
  - Provides default theme
  - Loads from localStorage
  - Toggles theme
  - Sets document attributes
  - Error handling

## Test Utilities

### Setup File (`src/test/setup.js`)
- Configures jest-dom matchers
- Sets up cleanup after each test
- Mocks window.matchMedia
- Mocks IntersectionObserver

### Test Utils (`src/test/test-utils.jsx`)
- `renderWithProviders`: Custom render function with all providers

## Writing New Tests

### Component Test Example

```jsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import MyComponent from './MyComponent';

describe('MyComponent', () => {
  it('renders correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });

  it('handles user interaction', async () => {
    const user = userEvent.setup();
    render(<MyComponent />);
    
    const button = screen.getByRole('button');
    await user.click(button);
    
    expect(screen.getByText('Clicked')).toBeInTheDocument();
  });
});
```

### Hook Test Example

```jsx
import { describe, it, expect } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useMyHook } from './useMyHook';

describe('useMyHook', () => {
  it('returns initial value', () => {
    const { result } = renderHook(() => useMyHook());
    expect(result.current.value).toBe('initial');
  });

  it('updates value', () => {
    const { result } = renderHook(() => useMyHook());
    
    act(() => {
      result.current.setValue('new');
    });
    
    expect(result.current.value).toBe('new');
  });
});
```

## Best Practices

1. **Test Behavior, Not Implementation**: Focus on what the component does, not how it does it.

2. **Use Semantic Queries**: Prefer `getByRole`, `getByLabelText` over `getByTestId`.

3. **Test User Interactions**: Use `@testing-library/user-event` for realistic user interactions.

4. **Mock External Dependencies**: Mock API calls, localStorage, and other external dependencies.

5. **Clean Up**: Tests should clean up after themselves (handled automatically by setup.js).

6. **Descriptive Test Names**: Use clear, descriptive test names that explain what is being tested.

7. **Arrange-Act-Assert**: Structure tests with clear sections for setup, action, and assertion.

## Coverage Goals

- **Components**: 80%+ coverage
- **Hooks**: 90%+ coverage
- **Services**: 90%+ coverage
- **Utilities**: 100% coverage
- **Contexts**: 90%+ coverage

## Continuous Integration

Tests should be run in CI/CD pipeline before deployment. Add this to your CI configuration:

```yaml
- name: Run tests
  run: |
    cd frontend
    npm install
    npm test -- --run
```

## Troubleshooting

### Tests not running
- Ensure all dependencies are installed: `npm install`
- Check that Vitest is properly configured in `vite.config.ts`

### Mocking issues
- Ensure mocks are reset between tests using `beforeEach` and `afterEach`
- Check that mocks are properly scoped

### Async issues
- Use `waitFor` for async operations
- Use `act` when updating state in tests

## Resources

- [Vitest Documentation](https://vitest.dev/)
- [React Testing Library](https://testing-library.com/react)
- [Testing Best Practices](https://kentcdodds.com/blog/common-mistakes-with-react-testing-library)



