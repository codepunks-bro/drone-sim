import * as THREE from "https://unpkg.com/three@0.161.0/build/three.module.js";
import { WsClient } from "./net/ws.js";

const canvas = document.getElementById("scene");
const throttleEl = document.getElementById("throttle");
const pitchEl = document.getElementById("pitch");
const rollEl = document.getElementById("roll");
const yawEl = document.getElementById("yaw");
const telemetryEl = document.getElementById("telemetry");
const runEl = document.getElementById("run");
const stopEl = document.getElementById("stop");
const scriptEl = document.getElementById("script");
const cameraFrameEl = document.getElementById("camera-frame");
const testStartEl = document.getElementById("test-start");
const testStopEl = document.getElementById("test-stop");
const testStatusEl = document.getElementById("test-status");
const loadAutopilotEl = document.getElementById("load-autopilot");
const runAutopilotEl = document.getElementById("run-autopilot");

const scene = new THREE.Scene();
scene.background = new THREE.Color(0x0a0a0a);
const camera = new THREE.PerspectiveCamera(60, 1, 0.1, 500);
camera.position.set(8, 8, 8);
camera.lookAt(0, 0, 0);

const renderer = new THREE.WebGLRenderer({ canvas });
renderer.setPixelRatio(window.devicePixelRatio || 1);

const light = new THREE.DirectionalLight(0xffffff, 1.0);
light.position.set(5, 10, 7);
scene.add(light);
scene.add(new THREE.AmbientLight(0xffffff, 0.3));

const grid = new THREE.GridHelper(40, 40);
scene.add(grid);

const drone = new THREE.Mesh(
  new THREE.BoxGeometry(0.6, 0.2, 0.6),
  new THREE.MeshStandardMaterial({ color: 0x2d7ff9 })
);
scene.add(drone);

const cameraOffset = new THREE.Vector3(8, 6, 8);
const keyboardState = {
  ArrowUp: false,
  ArrowDown: false,
  ArrowLeft: false,
  ArrowRight: false,
};
const KEY_PITCH = 1.2;
const KEY_ROLL = 1.2;

function resize() {
  const width = canvas.clientWidth;
  const height = canvas.clientHeight;
  renderer.setSize(width, height, false);
  camera.aspect = width / height;
  camera.updateProjectionMatrix();
}
window.addEventListener("resize", resize);
resize();

function getCommand() {
  const command = {
    throttle: parseFloat(throttleEl.value),
    pitch: parseFloat(pitchEl.value),
    roll: parseFloat(rollEl.value),
    yaw: parseFloat(yawEl.value),
  };
  const keyboard = getKeyboardCommand();
  if (keyboard.active) {
    command.pitch = keyboard.pitch;
    command.roll = keyboard.roll;
  }
  return command;
}

function getKeyboardCommand() {
  let pitch = 0;
  let roll = 0;
  if (keyboardState.ArrowUp) {
    pitch -= KEY_PITCH;
  }
  if (keyboardState.ArrowDown) {
    pitch += KEY_PITCH;
  }
  if (keyboardState.ArrowLeft) {
    roll -= KEY_ROLL;
  }
  if (keyboardState.ArrowRight) {
    roll += KEY_ROLL;
  }
  return {
    active: pitch !== 0 || roll !== 0,
    pitch,
    roll,
  };
}

function isEditableTarget(target) {
  if (!(target instanceof HTMLElement)) {
    return false;
  }
  const tag = target.tagName.toLowerCase();
  return tag === "input" || tag === "textarea" || target.isContentEditable;
}

function handleKeyChange(event, isDown) {
  if (isEditableTarget(event.target)) {
    return;
  }
  if (event.key in keyboardState) {
    keyboardState[event.key] = isDown;
    event.preventDefault();
  }
}

window.addEventListener("keydown", (event) => handleKeyChange(event, true));
window.addEventListener("keyup", (event) => handleKeyChange(event, false));
window.addEventListener("blur", () => {
  for (const key of Object.keys(keyboardState)) {
    keyboardState[key] = false;
  }
});

const apiHost = location.hostname || "127.0.0.1";
const apiBase = `http://${apiHost}:8000`;
const ws = new WsClient(
  `ws://${apiHost}:8000/ws`,
  (telemetry) => {
    const pos = telemetry.pos || [0, 0, 0];
    const rot = telemetry.rot || [0, 0, 0];
    drone.position.set(pos[0], pos[2], pos[1]);
    drone.rotation.set(rot[1], rot[2], rot[0]);
    telemetryEl.textContent = JSON.stringify(telemetry, null, 2);
  },
  (cameraMsg) => {
    if (cameraMsg.jpeg) {
      cameraFrameEl.src = `data:image/jpeg;base64,${cameraMsg.jpeg}`;
    }
  }
);
ws.connect();

setInterval(() => {
  ws.sendCommand(getCommand());
}, 50);

const autopilotScript = `def run(sdk):
    import time
    hover_throttle = 0.6
    rate_limit = 0.8
    gain = 0.9
    search_yaw = 0.4
    offset_limit = 0.12
    area_min = 150.0
    required_stable = 8
    stable_frames = 0

    while not sdk.should_stop():
        vision = sdk.get_vision(timeout=0.2)
        if not vision or not vision.get("target_visible"):
            sdk.set_command(hover_throttle, 0.0, 0.0, search_yaw)
            stable_frames = 0
            time.sleep(0.02)
            continue

        offset_x, offset_y = vision.get("target_offset", [0.0, 0.0])
        area = float(vision.get("target_area", 0.0))
        if (
            abs(offset_x) <= offset_limit
            and abs(offset_y) <= offset_limit
            and area >= area_min
        ):
            stable_frames += 1
        else:
            stable_frames = 0

        if stable_frames >= required_stable:
            sdk.set_command(hover_throttle, 0.0, 0.0, 0.0)
            time.sleep(0.05)
            continue

        pitch_rate = max(-rate_limit, min(rate_limit, offset_x * gain))
        roll_rate = max(-rate_limit, min(rate_limit, -offset_y * gain))
        sdk.set_command(hover_throttle, pitch_rate, roll_rate, 0.0)
        time.sleep(0.02)
`;

runEl.addEventListener("click", async () => {
  await fetch(`${apiBase}/scripts/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: scriptEl.value }),
  });
});

stopEl.addEventListener("click", async () => {
  await fetch(`${apiBase}/scripts/stop`, { method: "POST" });
});

loadAutopilotEl.addEventListener("click", () => {
  scriptEl.value = autopilotScript;
});

runAutopilotEl.addEventListener("click", async () => {
  scriptEl.value = autopilotScript;
  await fetch(`${apiBase}/scripts/run`, {
    method: "POST",
    headers: { "Content-Type": "application/json" },
    body: JSON.stringify({ source: scriptEl.value }),
  });
});

testStartEl.addEventListener("click", async () => {
  await fetch(`${apiBase}/tests/start`, { method: "POST" });
});

testStopEl.addEventListener("click", async () => {
  await fetch(`${apiBase}/tests/stop`, { method: "POST" });
});

async function refreshTestStatus() {
  try {
    const response = await fetch(`${apiBase}/tests/status`);
    if (!response.ok) {
      return;
    }
    const data = await response.json();
    testStatusEl.textContent = JSON.stringify(data, null, 2);
  } catch (error) {
    // Ignore transient test status errors.
  }
}

setInterval(refreshTestStatus, 500);

function animate() {
  requestAnimationFrame(animate);
  const desiredCameraPosition = drone.position.clone().add(cameraOffset);
  camera.position.lerp(desiredCameraPosition, 0.08);
  camera.lookAt(drone.position);
  renderer.render(scene, camera);
}
animate();
