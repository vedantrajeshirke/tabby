export type Status = {
  tesseract_available: boolean;
  tesseract_help: string | null;
  mock_mode: boolean;
  auth_mode: string;
};

export type Issue = { code: string; severity: "error" | "warning"; field: string | null; message: string };
export type Duplicate = { kind: "exact" | "likely"; expense_id: number; message: string; summary: string };

export type Report = {
  issues: Issue[];
  blocks_save: boolean;
  category: string;
  category_source: string;
  category_label: string;
  duplicates: Duplicate[];
};

export type Extraction = {
  document_type: string;
  merchant: string | null;
  date: string | null;
  currency: string | null;
  subtotal: number | null;
  tax: number | null;
  tip: number | null;
  total: number | null;
  payment_method: string | null;
  line_items: unknown[];
  field_confidence: Record<string, string>;
  field_reason: Record<string, string>;
  text_source: string;
  text_confidence: number;
  raw_text: string;
};

export type Upload = Report & { extraction: Extraction; file_hash: string; suggested_date: string };

export type ExpenseBody = {
  merchant: string;
  date: string;
  total: number | null;
  subtotal: number | null;
  tax: number | null;
  tip: number | null;
  payment_method: string | null;
  note: string;
  category: string | null;
  always_use_category: boolean;
  client_today: string;
  extraction: Extraction | null;
  file_hash: string | null;
};

export type SavedExpense = {
  id: number;
  merchant: string;
  date: string;
  total: number;
  currency: string;
  subtotal: number | null;
  tax: number | null;
  tip: number | null;
  category: string;
  category_label: string;
  payment_method: string | null;
  note: string | null;
  is_synthetic: boolean;
};
export type ExpenseDetail = SavedExpense & { extraction: Extraction | null };
export type Period = { start: string; end: string; label: string };

export class ApiError extends Error {
  constructor(
    message: string,
    readonly status: number,
    readonly report: Report | null = null,
  ) {
    super(message);
  }
}

export const LIST_LIMIT = 1000;
const BASE = import.meta.env.VITE_API_URL ?? "";
const CONNECTION_PROBLEM = "Can't reach SnapSpend. Check your connection and try again.";

let getToken: () => Promise<string | null> = async () => null;
let onSignedOut: () => void = () => {};

export function setAuthHandlers(token: typeof getToken, signedOut: typeof onSignedOut) {
  getToken = token;
  onSignedOut = signedOut;
}

async function request<T>(path: string, init: RequestInit = {}): Promise<T> {
  const headers = new Headers(init.headers);
  const token = await getToken();
  if (token) headers.set("Authorization", `Bearer ${token}`);

  let response: Response;
  try {
    response = await fetch(`${BASE}/api${path}`, { ...init, headers });
  } catch (e) {
    if (e instanceof DOMException && e.name === "AbortError") throw e;
    throw new ApiError(CONNECTION_PROBLEM, 0);
  }
  if (response.status === 204) return undefined as T;
  if (response.ok) return response.json();

  const body = await response.json().catch(() => null);
  if (response.status === 401) onSignedOut();
  const detail = body?.detail;
  if (detail && typeof detail === "object") throw new ApiError(detail.message, response.status, detail);
  throw new ApiError(typeof detail === "string" ? detail : "Something went wrong. Please try again.", response.status);
}

function postJson<T>(path: string, body: unknown, signal?: AbortSignal): Promise<T> {
  return request(path, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(body),
    signal,
  });
}

export function getStatus(): Promise<Status> {
  return request("/status");
}

export function getCategories(): Promise<string[]> {
  return request("/categories");
}

export function uploadFile(file: File, clientToday: string, signal: AbortSignal): Promise<Upload> {
  const form = new FormData();
  form.append("file", file);
  form.append("client_today", clientToday);
  return request("/extractions", { method: "POST", body: form, signal });
}

export function validateExpense(body: ExpenseBody, signal: AbortSignal): Promise<Report> {
  return postJson("/validate", body, signal);
}

export function saveExpense(body: ExpenseBody): Promise<{ expense: SavedExpense }> {
  return postJson("/expenses", body);
}

export function getPeriods(clientToday: string): Promise<Period[]> {
  return request(`/periods?client_today=${clientToday}`);
}

export function listExpenses(
  filters: { start?: string; end?: string; category?: string },
  signal: AbortSignal,
): Promise<SavedExpense[]> {
  const query = new URLSearchParams({ limit: String(LIST_LIMIT) });
  for (const [key, value] of Object.entries(filters)) if (value) query.set(key, value);
  return request(`/expenses?${query}`, { signal });
}

export function getExpense(id: string, signal: AbortSignal): Promise<ExpenseDetail> {
  return request(`/expenses/${encodeURIComponent(id)}`, { signal });
}

function editFields(body: ExpenseBody) {
  const { extraction: _extraction, file_hash: _fileHash, ...fields } = body;
  return fields;
}

export function validateEdit(id: number, body: ExpenseBody, signal: AbortSignal): Promise<Report> {
  return postJson(`/expenses/${id}/validate`, editFields(body), signal);
}

export function updateExpense(id: number, body: ExpenseBody): Promise<{ expense: SavedExpense }> {
  return request(`/expenses/${id}`, {
    method: "PATCH",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify(editFields(body)),
  });
}

export function deleteExpense(id: number): Promise<void> {
  return request(`/expenses/${id}`, { method: "DELETE" });
}
