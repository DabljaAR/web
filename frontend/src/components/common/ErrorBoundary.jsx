import React, { Component } from 'react';
import './ErrorBoundary.css';

export class ErrorBoundary extends Component {
  constructor(props) {
    super(props);
    this.state = { hasError: false, error: null };
  }

  static getDerivedStateFromError(error) {
    return { hasError: true, error };
  }

  componentDidCatch(error, info) {
    // In a real app, you would log to a service like Sentry
    console.error('ErrorBoundary caught:', error, info);
  }

  handleReload = () => {
    window.location.reload();
  };

  render() {
    if (this.state.hasError) {
      if (this.props.fallback) {
        return this.props.fallback;
      }

      return (
        <div className="error-boundary-page">
          <div className="error-content">
            <h1>Oops! Something went wrong.</h1>
            <p>We've encountered an unexpected error. Please try refreshing the page.</p>
            <div className="error-details">
              <code>{this.state.error && this.state.error.toString()}</code>
            </div>
            <button onClick={this.handleReload} className="reload-btn">
              Refresh Page
            </button>
          </div>
        </div>
      );
    }

    return this.props.children;
  }
}

export default ErrorBoundary;
