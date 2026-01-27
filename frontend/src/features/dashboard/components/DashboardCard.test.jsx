import { describe, it, expect } from 'vitest';
import { render, screen } from '@testing-library/react';
import DashboardCard from './DashboardCard';

describe('DashboardCard Component', () => {
  it('renders card with title and value', () => {
    render(<DashboardCard title="Total Users" value="1,234" />);
    
    expect(screen.getByText(/total users/i)).toBeInTheDocument();
    expect(screen.getByText(/1,234/i)).toBeInTheDocument();
  });

  it('renders card with icon', () => {
    const icon = <span data-testid="icon">📊</span>;
    render(<DashboardCard title="Stats" value="100" icon={icon} />);
    
    expect(screen.getByTestId('icon')).toBeInTheDocument();
  });

  it('applies custom className', () => {
    const { container } = render(
      <DashboardCard title="Test" value="0" className="custom-class" />
    );
    
    const card = container.querySelector('.custom-class');
    expect(card).toBeInTheDocument();
  });

  it('renders without icon', () => {
    render(<DashboardCard title="No Icon" value="50" />);
    
    expect(screen.getByText(/no icon/i)).toBeInTheDocument();
    expect(screen.getByText(/50/i)).toBeInTheDocument();
  });

  it('displays formatted values correctly', () => {
    render(<DashboardCard title="Revenue" value="$10,000" />);
    
    expect(screen.getByText(/\$10,000/i)).toBeInTheDocument();
  });
});



