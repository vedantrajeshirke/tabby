import { useEffect, useRef, useState, type DragEvent } from "react";
import { Link, useLocation } from "react-router";
import { ApiError, getCategories, uploadFile, type Extraction, type SavedExpense, type Upload } from "../api";
import ConfirmForm from "../components/ConfirmForm";
import { formatMoney, localToday } from "../format";

const MAX_BYTES = 10 * 1024 * 1024;
const ACCEPT = ".jpg,.jpeg,.png,.webp,.heic,.pdf,image/*,application/pdf";
const UNUSABLE = new Set(["unreadable", "not_an_expense"]);

const PRIVACY = {
  local: "Your receipts are processed and stored only on this device.",
  hosted: "Your receipt is read and then discarded. The details you save stay in your private account, and you can delete them at any time.",
};

const PHOTO_TIPS = ["Lay the receipt flat in good light", "Fit the whole receipt in the frame", "Hold steady and avoid shadows"];

type Stage =
  | { name: "pick" }
  | { name: "reading" }
  | { name: "unusable"; upload: Upload }
  | { name: "confirm"; upload: Upload | null }
  | { name: "saved"; expense: SavedExpense };

/** The browser's own copy of the file. It's never sent anywhere for previewing. */
function useFilePreview(file: File | null) {
  const [url, setUrl] = useState<string | null>(null);
  useEffect(() => {
    if (!file) return;
    const objectUrl = URL.createObjectURL(file);
    setUrl(objectUrl);
    return () => {
      URL.revokeObjectURL(objectUrl);
      setUrl(null);
    };
  }, [file]);
  return url;
}

export default function AddExpense({ localMode }: { localMode: boolean }) {
  const [stage, setStage] = useState<Stage>({ name: "pick" });
  const [file, setFile] = useState<File | null>(null);
  const [error, setError] = useState("");
  const [dragging, setDragging] = useState(false);
  const [categories, setCategories] = useState<string[]>([]);
  const reading = useRef<AbortController | null>(null);
  const previewUrl = useFilePreview(file);
  const { pathname } = useLocation();

  useEffect(() => {
    getCategories().then(setCategories).catch(() => setError("Couldn't load the categories. Refresh this page to try again."));
  }, []);

  useEffect(() => () => reading.current?.abort(), []);

  // Unsaved work survives leaving this page, but a finished save doesn't need to.
  useEffect(() => {
    if (pathname !== "/") setStage((current) => (current.name === "saved" ? { name: "pick" } : current));
  }, [pathname]);

  function reset() {
    reading.current?.abort();
    setFile(null);
    setError("");
    setStage({ name: "pick" });
  }

  async function read(chosen: File) {
    setError("");
    if (chosen.size > MAX_BYTES) {
      setError("This file is larger than 10 MB. Upload a smaller copy or enter the expense manually.");
      return;
    }
    const controller = new AbortController();
    reading.current = controller;
    setFile(chosen);
    setStage({ name: "reading" });
    try {
      const upload = await uploadFile(chosen, localToday(), controller.signal);
      setStage(UNUSABLE.has(upload.extraction.document_type) ? { name: "unusable", upload } : { name: "confirm", upload });
    } catch (e) {
      if (controller.signal.aborted) return;
      setFile(null);
      setStage({ name: "pick" });
      setError(e instanceof ApiError ? e.message : "This file couldn't be read. Try again or enter the expense manually.");
    }
  }

  function onDrop(event: DragEvent) {
    event.preventDefault();
    setDragging(false);
    const dropped = event.dataTransfer.files[0];
    if (dropped) read(dropped);
  }

  if (stage.name === "confirm") {
    return (
      <ConfirmForm
        upload={stage.upload}
        file={file}
        previewUrl={previewUrl}
        categories={categories}
        onDiscard={reset}
        onSaved={(expense) => {
          setFile(null);
          setStage({ name: "saved", expense });
        }}
      />
    );
  }

  if (stage.name === "saved") {
    const { expense } = stage;
    return (
      <section className="mx-auto max-w-md pt-6 text-center">
        <span aria-hidden="true" className="mx-auto grid size-12 place-items-center rounded-full bg-mint text-xl text-pine">✓</span>
        <div role="status">
          <h1 className="mt-4 text-2xl font-semibold tracking-tight text-pine">Expense saved</h1>
        </div>
        <div className="mt-6 rounded-2xl border border-line p-6">
          <p className="amount text-4xl font-semibold">{formatMoney(expense.total)}</p>
          <p className="mt-2 font-medium text-pine">{expense.merchant}</p>
          <p className="mt-1 text-sm text-muted">{expense.date} · {expense.category}</p>
        </div>
        <div className="mt-6 flex justify-center gap-3">
          <button onClick={reset} className="rounded-xl bg-forest px-5 py-3 font-medium text-white transition-colors hover:bg-pine">
            Add another
          </button>
          <Link to="/expenses" className="rounded-xl border border-line px-5 py-3 font-medium text-pine transition-colors hover:bg-mint">
            View expenses
          </Link>
        </div>
      </section>
    );
  }

  if (stage.name === "unusable") {
    return <Unusable extraction={stage.upload.extraction} message={stage.upload.issues[0]?.message} onRetry={reset} onManual={() => setStage({ name: "confirm", upload: stage.upload })} />;
  }

  return (
    <section>
      <h1 className="text-3xl font-semibold tracking-tight text-pine">Add expense</h1>
      <p className="mt-2 text-muted">Upload a receipt and check the details. Nothing is saved until you confirm.</p>

      {error && <p role="alert" className="mt-4 rounded-xl bg-expense-soft p-3 text-sm text-expense">{error}</p>}

      {stage.name === "reading" ? (
        <div role="status" className="mt-6 flex flex-col items-center rounded-2xl border border-line p-12 text-center">
          <span aria-hidden="true" className="size-8 animate-spin rounded-full border-3 border-mint border-t-forest" />
          <p className="mt-4 font-medium text-pine">Reading your receipt…</p>
          <p className="mt-1 text-sm text-muted">This can take a few seconds.</p>
          <button onClick={reset} className="mt-4 text-sm font-medium text-forest hover:underline">Cancel</button>
        </div>
      ) : (
        <label
          onDragOver={(e) => {
            e.preventDefault();
            setDragging(true);
          }}
          onDragLeave={() => setDragging(false)}
          onDrop={onDrop}
          className={`mt-6 flex cursor-pointer flex-col items-center rounded-2xl border-2 border-dashed p-10 text-center transition-colors focus-within:border-forest md:p-14 ${
            dragging ? "border-forest bg-mint" : "border-sage hover:bg-mint/40"
          }`}
        >
          <span aria-hidden="true" className="grid size-12 place-items-center rounded-full bg-mint text-pine">
            <svg viewBox="0 0 24 24" className="size-6" fill="none" stroke="currentColor" strokeWidth="1.75" strokeLinecap="round" strokeLinejoin="round">
              <path d="M12 16V5M7.5 9.5 12 5l4.5 4.5M5 19h14" />
            </svg>
          </span>
          <span className="mt-4 font-medium text-pine">Take a photo or choose a file</span>
          <span className="mt-1 text-sm text-muted">JPG, PNG, WEBP, HEIC or PDF, up to 10 MB</span>
          <input
            type="file"
            accept={ACCEPT}
            className="sr-only"
            onChange={(e) => {
              const chosen = e.target.files?.[0];
              e.target.value = ""; // lets the same file be chosen again
              if (chosen) read(chosen);
            }}
          />
        </label>
      )}

      {stage.name === "pick" && (
        <>
          <button
            onClick={() => setStage({ name: "confirm", upload: null })}
            className="mt-3 w-full rounded-xl border border-sage bg-mint px-4 py-3 font-medium text-pine transition-colors hover:bg-sage active:bg-sage"
          >
            Enter manually instead
          </button>
          <div className="mt-6 grid gap-6 border-t border-line pt-6 md:grid-cols-2">
            <div>
              <h2 className="text-sm font-semibold text-pine">For the best read</h2>
              <PhotoTips />
            </div>
            <div>
              <h2 className="text-sm font-semibold text-pine">Your privacy</h2>
              <p className="mt-2 text-sm text-muted">{localMode ? PRIVACY.local : PRIVACY.hosted}</p>
            </div>
          </div>
        </>
      )}
    </section>
  );
}

function PhotoTips() {
  return (
    <ul className="mt-2 space-y-1.5 text-sm text-muted">
      {PHOTO_TIPS.map((tip) => (
        <li key={tip} className="flex items-center gap-2">
          <span aria-hidden="true" className="size-1.5 shrink-0 rounded-full bg-sage" />
          {tip}
        </li>
      ))}
    </ul>
  );
}

function Unusable({ extraction, message, onRetry, onManual }: {
  extraction: Extraction;
  message?: string;
  onRetry: () => void;
  onManual: () => void;
}) {
  return (
    <section className="mx-auto max-w-md pt-6">
      <h1 className="text-2xl font-semibold tracking-tight text-pine">We couldn't fill this in</h1>
      <p role="alert" className="mt-3 text-muted">
        {message ?? extraction.field_reason.document_type ?? "This file couldn't be read clearly enough."}
      </p>
      <div className="mt-6 rounded-2xl border border-line p-5">
        <h2 className="text-sm font-semibold text-pine">For a clearer photo</h2>
        <PhotoTips />
      </div>
      <div className="mt-6 grid gap-3 sm:grid-cols-2">
        <button onClick={onRetry} className="rounded-xl bg-forest px-4 py-3 font-medium text-white transition-colors hover:bg-pine">
          Upload a clearer photo
        </button>
        <button onClick={onManual} className="rounded-xl border border-sage bg-mint px-4 py-3 font-medium text-pine transition-colors hover:bg-sage active:bg-sage">
          Enter manually
        </button>
      </div>
    </section>
  );
}
