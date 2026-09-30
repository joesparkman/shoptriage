import { useState } from "react";
import Dashboard from "./components/Dashboard.jsx";
import DemoConsole from "./components/DemoConsole.jsx";
import CallbackBoard from "./components/CallbackBoard.jsx";
import StaffInbox from "./components/StaffInbox.jsx";
import About from "./components/About.jsx";

const TABS = [
  { id: "dashboard", label: "Dashboard" },
  { id: "demo", label: "Demo Console" },
  { id: "board", label: "Callback Board" },
  { id: "inbox", label: "Staff Inbox" },
  { id: "about", label: "About" },
];

// Deep links like /#board open that tab directly.
function tabFromHash() {
  const id = window.location.hash.slice(1);
  return TABS.some((t) => t.id === id) ? id : "dashboard";
}

export default function App() {
  const [tab, setTabState] = useState(tabFromHash);

  function setTab(id) {
    setTabState(id);
    window.history.replaceState(null, "", `#${id}`);
  }

  return (
    <div className="app">
      <header className="app-header">
        <div className="brand">
          <span className="badge">AWS Zero to Shipped Hackathon 2026</span>
          <h1>Shop<span>Triage</span></h1>
        </div>
        <nav className="tabs">
          {TABS.map((t) => (
            <button
              key={t.id}
              className={`tab ${tab === t.id ? "tab-active" : ""}`}
              onClick={() => setTab(t.id)}
            >
              {t.label}
            </button>
          ))}
        </nav>
      </header>

      <main className="app-main">
        {tab === "dashboard" && <Dashboard />}
        {tab === "demo" && <DemoConsole />}
        {tab === "board" && <CallbackBoard />}
        {tab === "inbox" && <StaffInbox />}
        {tab === "about" && <About />}
      </main>
    </div>
  );
}
