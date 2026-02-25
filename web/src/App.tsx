import { Routes, Route } from "react-router-dom";
import AppLayout from "./components/AppLayout";
import ProjectList from "./pages/ProjectList";
import ProjectForm from "./pages/ProjectForm";
import ProjectDetail from "./pages/ProjectDetail";
import GlobalSettings from "./pages/GlobalSettings";
import StoryForm from "./pages/StoryForm";
import StoryDetail from "./pages/StoryDetail";
import LogViewer from "./pages/LogViewer";

export default function App() {
  return (
    <AppLayout>
      <Routes>
        <Route path="/" element={<ProjectList />} />
        <Route path="/logs" element={<LogViewer />} />
        <Route path="/settings" element={<GlobalSettings />} />
        <Route path="/projects/new" element={<ProjectForm />} />
        <Route path="/projects/:id" element={<ProjectDetail />} />
        <Route path="/projects/:id/edit" element={<ProjectForm />} />
        <Route path="/projects/:id/stories/new" element={<StoryForm />} />
        <Route path="/projects/:pid/stories/:id" element={<StoryDetail />} />
      </Routes>
    </AppLayout>
  );
}
