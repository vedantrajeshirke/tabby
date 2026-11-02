import { useEffect, useState } from "react";
import { NavLink, Route, Routes } from "react-router";
import { getStatus, type Status } from "./api";

const PAGES = [
  { path: "/", label: "Add", title: "Add Expense", next: "Upload and confirm arrive in M8." },
  { path: "/expenses", label: "Expenses", title: "Expenses", next: "The expense list arrives in M9." },
  { path: "/dashboard", label: "Dashboard", title: "Dashboard", next: "Charts and insights arrive in M10." },
  { path: "/settings", label: "Settings", title: "Settings", next: "Settings arrive in M11." },
];

function Placeholder({ title, next }: { title: string; next: string }) {
  return (
    <section>
      <h1 className="text-2xl font-semibold">{title}</h1>
      <p className="mt-2 text-gray-600">{next}</p>
    </section>
  );
}

export default function App() {
  const [status, setStatus] = useState<Status | null>(null);
  const [apiError, setApiError] = useState(false);

  useEffect(() => {
    getStatus().then(setStatus).catch(() => setApiError(true));
  }, []);

  return (
    <div className="mx-auto max-w-3xl px-4 py-4">
      <header className="mb-6">
        <p className="text-xl font-bold">🧾 SnapSpend</p>
        <nav className="mt-3 flex gap-4 border-b border-gray-200 pb-2">
          {PAGES.map((page) => (
            <NavLink
              key={page.path}
              to={page.path}
              end
              className={({ isActive }) => (isActive ? "font-semibold text-blue-700" : "text-gray-600")}
            >
              {page.label}
            </NavLink>
          ))}
        </nav>
      </header>

      {apiError && (
        <p role="alert" className="mb-4 rounded bg-red-50 p-3 text-red-800">
          Can't reach the SnapSpend API. Check that it's running, then refresh this page.
        </p>
      )}
      {status?.mock_mode && (
        <p role="status" className="mb-4 rounded bg-yellow-50 p-3 font-semibold text-yellow-900">
          MOCK MODE — extraction is simulated
        </p>
      )}
      {status && !status.tesseract_available && (
        <p role="status" className="mb-4 rounded bg-yellow-50 p-3 text-yellow-900">
          <strong>Tesseract OCR not found.</strong> Photo and scanned-PDF reading is disabled; manual entry, PDFs with
          a text layer, and the dashboard still work. {status.tesseract_help}
        </p>
      )}

      <main>
        <Routes>
          {PAGES.map((page) => (
            <Route key={page.path} path={page.path} element={<Placeholder title={page.title} next={page.next} />} />
          ))}
        </Routes>
      </main>
    </div>
  );
}
