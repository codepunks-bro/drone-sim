export class WsClient {
  constructor(url, onTelemetry, onCamera) {
    this.url = url;
    this.onTelemetry = onTelemetry;
    this.onCamera = onCamera;
    this.ws = null;
    this.isOpen = false;
  }

  connect() {
    this.ws = new WebSocket(this.url);
    this.ws.addEventListener("open", () => {
      this.isOpen = true;
    });
    this.ws.addEventListener("close", () => {
      this.isOpen = false;
      setTimeout(() => this.connect(), 1000);
    });
    this.ws.addEventListener("message", (event) => {
      try {
        const data = JSON.parse(event.data);
        if (data.type === "telemetry") {
          this.onTelemetry(data);
        } else if (data.type === "camera" && this.onCamera) {
          this.onCamera(data);
        }
      } catch (err) {
        console.error("WS parse error", err);
      }
    });
  }

  sendCommand(cmd) {
    if (!this.ws || !this.isOpen) return;
    this.ws.send(
      JSON.stringify({
        type: "command",
        throttle: cmd.throttle,
        pitch: cmd.pitch,
        roll: cmd.roll,
        yaw: cmd.yaw,
      })
    );
  }
}
