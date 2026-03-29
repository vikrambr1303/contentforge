/** Dispatched on `window` when a generation Celery task finishes (success or handled failure). */
export const JOB_DONE_EVENT = "contentforge:job-done";

/**
 * Maintains a WebSocket to `/api/ws` and dispatches {@link JOB_DONE_EVENT} for `job_done` payloads.
 * @returns {() => void} cleanup (close socket, cancel reconnect)
 */
export function connectGenerationRealtime() {
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  const url = `${proto}//${window.location.host}/api/ws`;
  let ws;
  let reconnectTimer;
  let closed = false;

  function scheduleReconnect() {
    if (closed) return;
    clearTimeout(reconnectTimer);
    reconnectTimer = window.setTimeout(connect, 2500);
  }

  function connect() {
    if (closed) return;
    try {
      ws = new WebSocket(url);
    } catch {
      scheduleReconnect();
      return;
    }
    ws.onmessage = (ev) => {
      try {
        const data = JSON.parse(ev.data);
        if (data.type === "job_done") {
          window.dispatchEvent(new CustomEvent(JOB_DONE_EVENT, { detail: data }));
        }
      } catch {
        /* ignore non-JSON */
      }
    };
    ws.onclose = () => scheduleReconnect();
    ws.onerror = () => {
      try {
        ws?.close();
      } catch {
        /* ignore */
      }
    };
  }

  connect();

  return () => {
    closed = true;
    clearTimeout(reconnectTimer);
    try {
      ws?.close();
    } catch {
      /* ignore */
    }
  };
}
