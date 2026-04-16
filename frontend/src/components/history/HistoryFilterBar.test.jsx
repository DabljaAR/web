import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import HistoryFilterBar from './HistoryFilterBar';

describe('HistoryFilterBar', () => {
  const t = (key) => key;

  it('switches tabs and updates filters through setters', () => {
    const setFilters = vi.fn();
    const setActiveMediaTab = vi.fn();

    const filters = {
      search: '',
      status: 'all',
      domain: 'all',
      dateRange: 'last30Days',
      sortBy: 'dateNewest',
      mediaType: 'all',
    };

    render(
      <HistoryFilterBar
        filters={filters}
        setFilters={setFilters}
        activeMediaTab="all"
        setActiveMediaTab={setActiveMediaTab}
        t={t}
      />
    );

    // Tab switching
    fireEvent.click(screen.getByRole('button', { name: 'history.tabVideos' }));
    expect(setActiveMediaTab).toHaveBeenCalledWith('video');

    // Search update calls setFilters with an updater function
    fireEvent.change(screen.getByRole('textbox'), { target: { name: 'search', value: 'abc' } });

    expect(setFilters).toHaveBeenCalledTimes(1);
    const updater = setFilters.mock.calls[0][0];
    expect(typeof updater).toBe('function');
    expect(updater(filters)).toEqual({ ...filters, search: 'abc' });

    // Status select update
    const selects = screen.getAllByRole('combobox');
    const statusSelect = selects[0];
    fireEvent.change(statusSelect, { target: { name: 'status', value: 'completed' } });

    const updater2 = setFilters.mock.calls[1][0];
    expect(updater2(filters)).toEqual({ ...filters, status: 'completed' });
  });
});
