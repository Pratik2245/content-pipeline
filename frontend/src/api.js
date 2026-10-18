// Thin client for the FastAPI backend (same-origin via Vite proxy).

export async function startRun(idea) {
  const res = await fetch("/api/run", {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ idea }),
  });
  if (!res.ok) {
    const detail = await res.text();
    throw new Error(detail || `HTTP ${res.status}`);
  }
  const data = await res.json();
  return data.run_id;
}

export function openStream(runId, handlers) {
  const es = new EventSource(`/api/stream/${runId}`);
  es.onmessage = (event) => {
    let data;
    try {
      data = JSON.parse(event.data);
    } catch {
      return;
    }
    switch (data.type) {
      case "log":
        handlers.onLog?.(data.line);
        break;
      case "posts":
        handlers.onPosts?.(data);
        break;
      case "image":
        handlers.onImage?.(data);
        break;
      case "done":
        handlers.onDone?.(data);
        break;
      case "error":
        handlers.onError?.(data.message);
        break;
      case "closed":
        handlers.onClosed?.();
        break;
    }
  };
  return es;
}
