import React, { useState, useCallback } from 'react';
import { Routes, Route, Link } from 'react-router-dom';
import Dashboard from './pages/Dashboard';
import './App.css';

function App() {
  const [refreshTrigger, setRefreshTrigger] = useState(0);

  const handleRefresh = useCallback(() => {
    setRefreshTrigger((prev) => prev + 1);
  }, []);

  return (
    <div className="app-container">
      <header className="app-header">
        <h1>Folder Sync System</h1>
        <div className="app-header-actions">
          <nav>
            <Link to="/">Dashboard</Link>
          </nav>
          <button onClick={handleRefresh} className="refresh-btn">
            Refresh
          </button>
        </div>
      </header>
      <main className="app-main">
        <Routes>
          <Route path="/" element={<Dashboard refreshTrigger={refreshTrigger} />} />
        </Routes>
      </main>
    </div>
  );
}

export default App;
