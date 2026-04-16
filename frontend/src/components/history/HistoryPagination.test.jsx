import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import HistoryPagination from './HistoryPagination';

describe('HistoryPagination', () => {
  const t = (key) => key;

  it('returns null when total is 0', () => {
    const { container } = render(
      <HistoryPagination
        pagination={{ page: 1, pages: 1, total: 0, limit: 10 }}
        setPagination={vi.fn()}
        t={t}
      />
    );

    expect(container).toBeEmptyDOMElement();
  });

  it('renders range info and updates page via setter', () => {
    const setPagination = vi.fn();

    const pagination = {
      page: 2,
      pages: 5,
      total: 50,
      limit: 10,
    };

    render(<HistoryPagination pagination={pagination} setPagination={setPagination} t={t} />);

    // Showing 11-20 of 50
    expect(screen.getByText(/history\.showing/i)).toBeInTheDocument();
    expect(screen.getByText(/11-20/i)).toBeInTheDocument();
    expect(screen.getByText(/history\.of/i)).toBeInTheDocument();

    // Prev button moves page back
    fireEvent.click(screen.getByRole('button', { name: 'history.prev' }));
    const updater = setPagination.mock.calls[0][0];
    expect(updater(pagination)).toEqual({ ...pagination, page: 1 });

    // Clicking page 4
    fireEvent.click(screen.getByRole('button', { name: '4' }));
    const updater2 = setPagination.mock.calls[1][0];
    expect(updater2(pagination)).toEqual({ ...pagination, page: 4 });
  });
});
