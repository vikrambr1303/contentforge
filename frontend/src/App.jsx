import { NavLink, Route, Routes } from "react-router-dom";
import ContentLibrary from "./pages/ContentLibrary.jsx";
import Dashboard from "./pages/Dashboard.jsx";
import Generate from "./pages/Generate.jsx";
import Platforms from "./pages/Platforms.jsx";
import SettingsPage from "./pages/Settings.jsx";
import Topics from "./pages/Topics.jsx";

const nav = [
  { to: "/", label: "Dashboard" },
  { to: "/topics", label: "Topics" },
  { to: "/generate", label: "Generate" },
  { to: "/library", label: "Content Library" },
  { to: "/platforms", label: "Platforms" },
  { to: "/settings", label: "Settings" },
];

function Layout({ children }) {
  return (
    <div className="min-h-screen flex flex-col">
      <header className="sticky top-0 z-20 border-b border-white/[0.06] bg-forge-950/75 backdrop-blur-md">
        <div className="max-w-7xl mx-auto px-4 sm:px-6 py-3.5 flex flex-wrap items-center gap-4 justify-between">
          <div className="flex items-center gap-3 min-w-0">
            <div className="h-8 w-8 rounded-lg bg-gradient-to-br from-sky-500 to-indigo-600 shadow-lg shadow-sky-900/40 shrink-0" aria-hidden />
            <div className="min-w-0">
              <span className="text-lg font-semibold tracking-tight text-white block leading-tight">ContentForge</span>
              <span className="text-[11px] text-slate-500 hidden sm:block">Local AI content studio</span>
            </div>
          </div>
          <nav className="flex flex-wrap gap-0.5 justify-end">
            {nav.map((item) => (
              <NavLink
                key={item.to}
                to={item.to}
                end={item.to === "/"}
                className={({ isActive }) =>
                  `px-3 py-2 rounded-lg text-sm font-medium transition ${
                    isActive
                      ? "bg-forge-800 text-sky-300 shadow-inner shadow-black/20 ring-1 ring-sky-500/20"
                      : "text-slate-400 hover:text-white hover:bg-forge-800/50"
                  }`
                }
              >
                {item.label}
              </NavLink>
            ))}
          </nav>
        </div>
      </header>
      <main className="flex-1 max-w-7xl w-full mx-auto px-4 sm:px-6 py-8 lg:py-10">{children}</main>
    </div>
  );
}

export default function App() {
  return (
    <Layout>
      <Routes>
        <Route path="/" element={<Dashboard />} />
        <Route path="/topics" element={<Topics />} />
        <Route path="/generate" element={<Generate />} />
        <Route path="/library" element={<ContentLibrary />} />
        <Route path="/platforms" element={<Platforms />} />
        <Route path="/settings" element={<SettingsPage />} />
      </Routes>
    </Layout>
  );
}
