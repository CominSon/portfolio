/** WebSocket: через прокси Vite (/ws) или VITE_WS_URL. */
export type WSMessage = {
  type: string;
  [key: string]: unknown;
};

type Handler = (msg: WSMessage) => void;

function wsBase(): string {
  const env = import.meta.env.VITE_WS_URL;
  if (env) return env.replace(/\/$/, "");
  const proto = window.location.protocol === "https:" ? "wss:" : "ws:";
  return `${proto}//${window.location.host}`;
}

export class InterviewWebSocket {
  private ws: WebSocket | null = null;
  private handlers: Handler[] = [];

  connect(interviewId: string, token: string) {
    const url = `${wsBase()}/ws/interviews/${interviewId}?token=${encodeURIComponent(token)}`;
    this.ws = new WebSocket(url);
    this.ws.onmessage = (ev) => {
      try {
        const msg = JSON.parse(ev.data) as WSMessage;
        this.handlers.forEach((h) => h(msg));
      } catch {
        /* ignore */
      }
    };
    return new Promise<void>((resolve, reject) => {
      if (!this.ws) return reject();
      this.ws.onopen = () => resolve();
      this.ws.onerror = () => reject(new Error("WebSocket failed"));
    });
  }

  onMessage(handler: Handler) {
    this.handlers.push(handler);
    return () => {
      this.handlers = this.handlers.filter((h) => h !== handler);
    };
  }

  send(msg: WSMessage) {
    if (this.ws?.readyState === WebSocket.OPEN) {
      this.ws.send(JSON.stringify(msg));
    }
  }

  disconnect() {
    this.ws?.close();
    this.ws = null;
  }
}
