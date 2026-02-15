import { Routes, Route } from 'react-router-dom';
import AppLayout from './components/AppLayout';
import ProjectList from './pages/ProjectList';
import ProjectForm from './pages/ProjectForm';
import ProjectDetail from './pages/ProjectDetail';
import ProjectSettings from './pages/ProjectSettings';
import StoryForm from './pages/StoryForm';
import StoryDetail from './pages/StoryDetail';

export default function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<ProjectList />} />
        <Route path="/projects/new" element={<ProjectForm />} />
        <Route path="/projects/:id" element={<ProjectDetail />} />
        <Route path="/projects/:id/edit" element={<ProjectForm />} />
        <Route path="/projects/:id/settings" element={<ProjectSettings />} />
        <Route path="/projects/:id/stories/new" element={<StoryForm />} />
        <Route path="/stories/:id" element={<StoryDetail />} />
      </Routes>
    </AppLayout>
  );
}
