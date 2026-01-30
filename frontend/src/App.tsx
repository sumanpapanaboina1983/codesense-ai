import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { Layout } from './components/Layout';
import {
  Dashboard,
  Analyze,
  Jobs,
  Chat,
  GenerateBRD,
  GenerateEPIC,
  GenerateBacklogs,
} from './pages';
import './App.css';

function App() {
  return (
    <BrowserRouter>
      <Layout>
        <Routes>
          <Route path="/" element={<Navigate to="/dashboard" replace />} />
          <Route path="/dashboard" element={<Dashboard />} />
          <Route path="/chat" element={<Chat />} />
          <Route path="/analyze" element={<Analyze />} />
          <Route path="/jobs" element={<Jobs />} />
          <Route path="/generate-brd" element={<GenerateBRD />} />
          <Route path="/generate-epic" element={<GenerateEPIC />} />
          <Route path="/generate-backlogs" element={<GenerateBacklogs />} />
        </Routes>
      </Layout>
    </BrowserRouter>
  );
}

export default App;
