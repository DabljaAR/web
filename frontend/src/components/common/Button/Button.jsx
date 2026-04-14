import React from 'react';
import '../../../styles/components.css';

const Button = ({ children, onClick, variant = 'primary', className = '', ...props }) => {
  const variantClass = `btn-vitals-${variant}`;

  return (
    <button
      className={`btn-vitals ${variantClass} ${className}`}
      onClick={onClick}
      {...props}
    >
      {children}
    </button>
  );
};

export default Button;

