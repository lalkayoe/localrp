import { HashRouter, Navigate, Route, Routes } from "react-router-dom";
import { useAuthStore } from "./store/authStore";
import NavRail from "./components/NavRail";
import LoginPage from "./pages/LoginPage";
import ChatPage from "./pages/ChatPage";
import MemoryEditorPage from "./pages/MemoryEditorPage";
import CharactersPage from "./pages/CharactersPage";
import TimelinePage from "./pages/TimelinePage";
import SearchPage from "./pages/SearchPage";
import SettingsPage from "./pages/SettingsPage";
import PromptInspectorPage from "./pages/PromptInspectorPage";
import "./styles/app-shell.css";

export default function App() {
  const isAuthenticated = useAuthStore((s) => s.isAuthenticated);

  if (!isAuthenticated) return <LoginPage />;

  return (
    <HashRouter>
      <div className="app-shell">
        <NavRail />
        <div className="app-content">
          <Routes>
            <Route path="/" element={<ChatPage />} />
            <Route path="/memory" element={<MemoryEditorPage />} />
            <Route path="/characters" element={<CharactersPage />} />
            <Route path="/timeline" element={<TimelinePage />} />
            <Route path="/search" element={<SearchPage />} />
            <Route path="/prompt-inspector" element={<PromptInspectorPage />} />
            <Route path="/settings" element={<SettingsPage />} />
            <Route path="*" element={<Navigate to="/" replace />} />
          </Routes>
        </div>
      </div>
    </HashRouter>
  );
}
