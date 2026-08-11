import React from 'react';
import FolderTable from '../components/FolderTable';
import './Dashboard.css';

type DashboardProps = {
  refreshTrigger: number;
};

const Dashboard: React.FC<DashboardProps> = ({ refreshTrigger }) => {
  return (
    <div className="dashboard">
      <FolderTable
        refreshTrigger={refreshTrigger}
      />
    </div>
  );
};

export default Dashboard;
