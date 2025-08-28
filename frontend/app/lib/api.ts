// app/lib/api.ts
export const API = process.env.NEXT_PUBLIC_API!;

export async function getTusEndpoint() {
  const r = await fetch(`${API}/uploads/tus`, { cache: "no-store" });
  if (!r.ok) throw new Error("tus endpoint failed");
  const j = await r.json();
  return j.tus_endpoint as string; // e.g. http://localhost:8080
}

export async function createSplit(tus_url: string) {
  const r = await fetch(`${API}/split`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tus_url }),
  });
  return r.json() as Promise<{ task_id: string }>;
}

export async function createMerge(video_tus_url: string, audio_tus_url: string, offset_sec = 0) {
  const r = await fetch(`${API}/merge`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ video_tus_url, audio_tus_url, offset_sec }),
  });
  return r.json() as Promise<{ task_id: string }>;
}

export async function createTranscribe(tus_url: string) {
  const r = await fetch(`${API}/transcribe`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ tus_url, target_languages: ["original"] }),
  });
  return r.json() as Promise<{ task_id: string }>;
}

export async function bulkRename(keys: string[], pattern: string, start_index = 1, pad = 2, dryRun = false) {
  const r = await fetch(`${API}/rename`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ keys, pattern, start_index, pad, dryRun }),
  });
  return r.json() as Promise<{ task_id: string }>;
}

export async function getJob(task_id: string) {
  const r = await fetch(`${API}/jobs/${task_id}`, { cache: "no-store" });
  return r.json() as Promise<{ state: string; result?: any; error?: string }>;
}
