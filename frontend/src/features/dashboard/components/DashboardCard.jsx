import React from 'react';

const DashboardCard = ({ title, value, icon, className = '' }) => {
  return (
    <div className={`bg-white rounded-lg shadow-md p-6 ${className}`}>
      <div className="flex items-center justify-between">
        <div>
          <p className="text-gray-600 text-sm font-medium">{title}</p>
          <p className="text-2xl font-bold text-gray-800 mt-2">{value}</p>
        </div>
        {icon && <div className="text-4xl text-gray-400">{icon}</div>}
      </div>
    </div>
  );
};

export default DashboardCard;

