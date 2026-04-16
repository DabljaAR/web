import React, { useId } from 'react';
import '../../../styles/components.css';

const Input = ({ label, type = 'text', value, onChange, placeholder, error, className = '', id, ...props }) => {
  const inputId = id || useId();
  
  return (
    <div className={`input-container ${className}`}>
      {label && (
        <label htmlFor={inputId} className="input-label">
          {label}
        </label>
      )}
      <input
        id={inputId}
        type={type}
        value={value}
        onChange={onChange}
        placeholder={placeholder}
        className={`input-field ${error ? 'error' : ''} ${className}`.trim()}
        aria-invalid={error ? 'true' : undefined}
        aria-describedby={error ? `${inputId}-error` : undefined}
        {...props}
      />
      {error && <p id={`${inputId}-error`} className="input-error-message" role="alert">{error}</p>}
    </div>
  );
};

export default Input;

