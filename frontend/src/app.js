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
  return {
    throttle: parseFloat(throttleEl.value),
    pitch: parseFloat(pitchEl.value),
    roll: parseFloat(rollEl.value),
    yaw: parseFloat(yawEl.value),
  };
}

const apiHost = location.hostname || "127.0.0.1";
const apiBase = `http://${apiHost}:8000`;
const ws = new WsClient(`ws://${apiHost}:8000/ws`, (telemetry) => {
  const pos = telemetry.pos || [0, 0, 0];
  const rot = telemetry.rot || [0, 0, 0];
  drone.position.set(pos[0], pos[2], pos[1]);
  drone.rotation.set(rot[1], rot[2], rot[0]);
  telemetryEl.textContent = JSON.stringify(telemetry, null, 2);
});
ws.connect();

setInterval(() => {
  ws.sendCommand(getCommand());
}, 50);

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

function animate() {
  requestAnimationFrame(animate);
  renderer.render(scene, camera);
}
animate();
