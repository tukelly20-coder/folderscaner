/**
 * WebSocket client for realtime folder updates.
 * Listens for events from the server and invokes a callback.
 */

type WSCallback = (data: any) => void;

class WSClient {
  private ws: WebSocket | null = null;
  private callbacks: WSCallback[] = [];
  private reconnectAttempts = 0;
  private readonly maxReconnectAttempts = 10;
  private readonly reconnectDelay = 2000;

  connect(baseUrl?: string): void {
    const proto = window.location.protocol === 'https:' ? 'wss:' : 'ws:';
    const host = baseUrl || window.location.host;
    const url = `${proto}//${host}/ws/folders`;

    this.ws = new WebSocket(url);

    this.ws.onopen = () => {
      console.log('[WS] Connected to', url);
      this.reconnectAttempts = 0;
    };

    this.ws.onmessage = (event) => {
      try {
        const data = JSON.parse(event.data);
        this.callbacks.forEach((cb) => cb(data));
      } catch (err) {
        console.error('[WS] Failed to parse message:', event.data, err);
      }
    };

    this.ws.onerror = (err) => {
      console.error('[WS] Error:', err);
    };

    this.ws.onclose = () => {
      console.log('[WS] Disconnected');
      if (this.reconnectAttempts < this.maxReconnectAttempts) {
        this.reconnectAttempts++;
        const delay = this.reconnectDelay * this.reconnectAttempts;
        console.log(`[WS] Reconnecting in ${delay}ms...`);
        setTimeout(() => this.connect(baseUrl), delay);
      }
    };
  }

  onMessage(cb: WSCallback): () => void {
    this.callbacks.push(cb);
    return () => {
      this.callbacks = this.callbacks.filter((c) => c !== cb);
    };
  }

  disconnect(): void {
    if (this.ws) {
      this.ws.close();
      this.ws = null;
    }
  }
}

export const wsClient = new WSClient();
