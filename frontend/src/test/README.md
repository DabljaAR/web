# Frontend Testing Guide

This directory contains the testing setup and utilities for the frontend application.

## Testing Stack

- **Vitest**: Fast unit test framework
- **React Testing Library**: React component testing utilities
- **@testing-library/jest-dom**: Custom Jest matchers for DOM assertions
- **@testing-library/user-event**: User interaction simulation

## Running Tests

```bash
# Run tests in watch mode
npm test

# Run tests with UI
npm run test:ui

# Run tests with coverage
npm run test:coverage
```

## Test Structure

Tests are co-located with their source files using the `.test.jsx` or `.test.js` extension pattern:

```
src/
  components/
    Button/
      Button.jsx
      Button.test.jsx
  hooks/
    useAuth.js
    useAuth.test.js
```

## Test Utilities

The `test-utils.jsx` file provides custom render functions and utilities:

- `renderWithProviders`: Renders components with all necessary providers (Router, Language, Theme)

## Writing Tests

### Component Tests

```jsx
import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import MyComponent from './MyComponent';

describe('MyComponent', () => {
  it('renders correctly', () => {
    render(<MyComponent />);
    expect(screen.getByText('Hello')).toBeInTheDocument();
  });
});
```

### Hook Tests

```jsx
import { describe, it, expect } from 'vitest';
import { renderHook } from '@testing-library/react';
import { useMyHook } from './useMyHook';

describe('useMyHook', () => {
  it('returns expected value', () => {
    const { result } = renderHook(() => useMyHook());
    expect(result.current.value).toBe('expected');
  });
});
```

### Service Tests

```jsx
import { describe, it, expect, vi } from 'vitest';
import { myService } from './myService';

describe('myService', () => {
  it('calls API correctly', async () => {
    global.fetch = vi.fn().mockResolvedValue({
      ok: true,
      json: async () => ({ data: 'test' }),
    });

    const result = await myService.getData();
    expect(result.data).toBe('test');
  });
});
```

## Coverage

The test suite aims for comprehensive coverage of:
- All components
- All hooks
- All services
- All utility functions
- All contexts

Run `npm run test:coverage` to see detailed coverage reports.



