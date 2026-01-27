import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import userEvent from '@testing-library/user-event';
import Input from './Input';

describe('Input Component', () => {
  it('renders input field', () => {
    render(<Input />);
    const input = screen.getByRole('textbox');
    expect(input).toBeInTheDocument();
  });

  it('renders with label', () => {
    render(<Input label="Username" />);
    expect(screen.getByLabelText(/username/i)).toBeInTheDocument();
  });

  it('displays placeholder text', () => {
    render(<Input placeholder="Enter your name" />);
    const input = screen.getByPlaceholderText(/enter your name/i);
    expect(input).toBeInTheDocument();
  });

  it('calls onChange handler when value changes', async () => {
    const handleChange = vi.fn();
    const user = userEvent.setup();
    render(<Input onChange={handleChange} />);
    
    const input = screen.getByRole('textbox');
    await user.type(input, 'test');
    
    expect(handleChange).toHaveBeenCalled();
  });

  it('displays error message when error prop is provided', () => {
    render(<Input error="This field is required" />);
    expect(screen.getByText(/this field is required/i)).toBeInTheDocument();
  });

  it('applies error styling when error is present', () => {
    render(<Input error="Error message" />);
    const input = screen.getByRole('textbox');
    expect(input.className).toContain('border-red-500');
  });

  it('renders with different input types', () => {
    const { rerender, container } = render(<Input type="email" />);
    let input = screen.getByRole('textbox');
    expect(input.type).toBe('email');

    rerender(<Input type="password" />);
    input = container.querySelector('input[type="password"]');
    expect(input.type).toBe('password');
  });

  it('displays value correctly', () => {
    render(<Input value="test value" onChange={() => {}} />);
    const input = screen.getByRole('textbox');
    expect(input.value).toBe('test value');
  });

  it('applies custom className', () => {
    render(<Input className="custom-input" />);
    const input = screen.getByRole('textbox');
    expect(input.className).toContain('custom-input');
  });

  it('passes through additional props', () => {
    render(<Input data-testid="test-input" required />);
    const input = screen.getByTestId('test-input');
    expect(input).toBeRequired();
  });
});

