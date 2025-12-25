export const formatStats = (stats) => {
  if (!stats) return null;

  return {
    totalUsers: stats.totalUsers || 0,
    totalRevenue: formatCurrency(stats.totalRevenue || 0),
    activeProjects: stats.activeProjects || 0,
    completionRate: `${stats.completionRate || 0}%`,
  };
};

export const formatCurrency = (amount) => {
  return new Intl.NumberFormat('en-US', {
    style: 'currency',
    currency: 'USD',
  }).format(amount);
};

