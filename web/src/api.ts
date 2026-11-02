export type Status = {
  tesseract_available: boolean;
  tesseract_help: string | null;
  mock_mode: boolean;
  auth_mode: string;
};

export async function getStatus(): Promise<Status> {
  const response = await fetch("/api/status");
  if (!response.ok) throw new Error(`Status request failed (${response.status})`);
  return response.json();
}
