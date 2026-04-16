import { expect, afterEach, vi } from 'vitest';
import { cleanup } from '@testing-library/react';
import * as matchers from '@testing-library/jest-dom/matchers';
import fs from 'node:fs';
import path from 'node:path';

// Extend Vitest's expect with jest-dom matchers
expect.extend(matchers);

// Ensure coverage temp directory exists (workaround for occasional ENOENT when writing v8 coverage files)
try {
  fs.mkdirSync(path.join(process.cwd(), 'coverage', '.tmp'), { recursive: true });
} catch (e) {
  // ignore
}

// Cleanup after each test
afterEach(() => {
  cleanup();
});

// Mock window.matchMedia
Object.defineProperty(window, 'matchMedia', {
  writable: true,
  value: (query) => ({
    matches: false,
    media: query,
    onchange: null,
    addListener: () => {},
    removeListener: () => {},
    addEventListener: () => {},
    removeEventListener: () => {},
    dispatchEvent: () => {},
  }),
});

// Mock IntersectionObserver
global.IntersectionObserver = class IntersectionObserver {
  constructor() {}
  disconnect() {}
  observe() {}
  takeRecords() {
    return [];
  }
  unobserve() {}
};

// Mock window.location to prevent navigation errors in jsdom
// This allows setting window.location.href without triggering navigation
if (typeof window !== 'undefined') {
  const locationMock = {
    href: '/',
    pathname: '/',
    assign: vi.fn(),
    replace: vi.fn(),
    reload: vi.fn(),
    search: '',
    hash: '',
    origin: 'http://localhost',
    protocol: 'http:',
    host: 'localhost',
    hostname: 'localhost',
    port: '',
  };

  // Make href writable
  Object.defineProperty(locationMock, 'href', {
    writable: true,
    configurable: true,
    value: '/',
  });

  Object.defineProperty(window, 'location', {
    value: locationMock,
    writable: true,
    configurable: true,
  });
}

