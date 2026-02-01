from __future__ import annotations

import asyncio
import base64
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional, Set

import cv2
from fastapi import FastAPI, Response, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .rl import RLTrainer, build_observation
from .rl.policy import PolicyModel
from .sim.camera import CameraConfig, render_topdown
from .sim.core import SimCore
from .sim.drone import ControlCommand
from .sim.recording import Recorder
from .sim.world import SphereObstacle, WorldState
from .scripting.host import ScriptHost
from .vision.processor import VisionProcessor


class ScriptRunRequest(BaseModel):
    source: str


class SceneModel(BaseModel):
    bounds: Dict[str, List[float]]
    obstacles: List[Dict[str, Any]]


class ControlModeRequest(BaseModel):
    mode: str


class TestStartRequest(BaseModel):
    max_time_s: Optional[float] = None
    target_offset_max: Optional[float] = None
    target_area_min: Optional[float] = None
    required_stable_frames: Optional[int] = None


@dataclass
class TestConfig:
    max_time_s: float = 25.0
    target_offset_max: float = 0.15
    target_area_min: float = 140.0
    required_stable_frames: int = 10


@dataclass
class TestState:
    running: bool = False
    passed: bool = False
    failed: bool = False
    reason: str = ""
    start_time_s: float = 0.0
    stable_frames: int = 0
    config: TestConfig = field(default_factory=TestConfig)

    def to_dict(self, sim_time_s: float) -> Dict[str, Any]:
        elapsed = max(0.0, sim_time_s - self.start_time_s) if self.running else 0.0
        return {
            "running": self.running,
            "passed": self.passed,
            "failed": self.failed,
            "reason": self.reason,
            "elapsed_s": elapsed,
            "stable_frames": self.stable_frames,
            "config": {
                "max_time_s": self.config.max_time_s,
                "target_offset_max": self.config.target_offset_max,
                "target_area_min": self.config.target_area_min,
                "required_stable_frames": self.config.required_stable_frames,
            },
        }


@dataclass
class AppState:
    sim: SimCore = field(default_factory=SimCore)
    script_host: ScriptHost = field(default_factory=ScriptHost)
    manual_command: ControlCommand = field(default_factory=ControlCommand)
    clients: Set[WebSocket] = field(default_factory=set)
    recorder: Recorder = field(default_factory=Recorder)
    camera: CameraConfig = field(default_factory=CameraConfig)
    vision: VisionProcessor = field(default_factory=VisionProcessor)
    latest_frame: Optional[Any] = None
    latest_frame_jpeg: Optional[bytes] = None
    camera_seq: int = 0
    camera_send_stride: int = 3
    test: TestState = field(default_factory=TestState)
    control_mode: str = "manual"
    rl_trainer: Optional[RLTrainer] = None
    scene_path: Path = field(
        default_factory=lambda: Path(__file__).resolve().parent / "data" / "scene.json"
    )


app = FastAPI()
state = AppState()

app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:5173", "http://localhost:5173"],
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)


def _build_default_world() -> WorldState:
    world = WorldState()
    world.obstacles = [
        SphereObstacle(center=[5.0, 5.0, 2.0], radius=1.5),
        SphereObstacle(center=[-6.0, 2.0, 3.0], radius=2.0),
    ]
    return world


def _start_test(req: Optional[TestStartRequest]) -> None:
    config = TestConfig()
    if req is not None:
        if req.max_time_s is not None:
            config.max_time_s = req.max_time_s
        if req.target_offset_max is not None:
            config.target_offset_max = req.target_offset_max
        if req.target_area_min is not None:
            config.target_area_min = req.target_area_min
        if req.required_stable_frames is not None:
            config.required_stable_frames = req.required_stable_frames
    state.test = TestState(
        running=True,
        passed=False,
        failed=False,
        reason="",
        start_time_s=state.sim.time_s,
        stable_frames=0,
        config=config,
    )


def _stop_test(reason: str = "stopped") -> None:
    state.test.running = False
    state.test.reason = reason


def _update_test(telemetry: Dict[str, Any]) -> None:
    test = state.test
    if not test.running:
        return
    sim_time_s = float(telemetry.get("time", state.sim.time_s))
    elapsed = sim_time_s - test.start_time_s
    if telemetry.get("collided"):
        test.running = False
        test.failed = True
        test.reason = "collision"
        return
    if elapsed >= test.config.max_time_s:
        test.running = False
        test.failed = True
        test.reason = "timeout"
        return

    vision = telemetry.get("vision") or {}
    target_visible = bool(vision.get("target_visible"))
    offset = vision.get("target_offset") or [0.0, 0.0]
    area = float(vision.get("target_area") or 0.0)
    if target_visible:
        if (
            abs(float(offset[0])) <= test.config.target_offset_max
            and abs(float(offset[1])) <= test.config.target_offset_max
            and area >= test.config.target_area_min
        ):
            test.stable_frames += 1
        else:
            test.stable_frames = 0
    else:
        test.stable_frames = 0

    if test.stable_frames >= test.config.required_stable_frames:
        test.running = False
        test.passed = True
        test.reason = "target_acquired"


@app.on_event("startup")
async def _startup() -> None:
    state.sim.world = _build_default_world()
    state.rl_trainer = RLTrainer(world=state.sim.world, camera=state.camera)
    state.rl_trainer.load()
    asyncio.create_task(simulation_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    state.script_host.stop()
    if state.rl_trainer is not None:
        state.rl_trainer.stop()


@app.websocket("/ws")
async def ws_endpoint(ws: WebSocket) -> None:
    await ws.accept()
    state.clients.add(ws)
    try:
        while True:
            data = await ws.receive_json()
            if data.get("type") == "command":
                state.manual_command.throttle = float(data.get("throttle", 0.0))
                state.manual_command.pitch = float(data.get("pitch", 0.0))
                state.manual_command.roll = float(data.get("roll", 0.0))
                state.manual_command.yaw = float(data.get("yaw", 0.0))
    except WebSocketDisconnect:
        state.clients.discard(ws)


@app.post("/scripts/run")
async def run_script(req: ScriptRunRequest) -> Dict[str, str]:
    state.script_host.start(req.source)
    state.control_mode = "script"
    return {"status": "started"}


@app.post("/scripts/stop")
async def stop_script() -> Dict[str, str]:
    state.script_host.stop()
    if state.control_mode == "script":
        state.control_mode = "manual"
    return {"status": "stopped"}


@app.get("/scripts/status")
async def script_status() -> Dict[str, str]:
    running = state.script_host.process is not None and state.script_host.process.is_alive()
    return {"status": "running" if running else "stopped"}


@app.get("/scene")
async def get_scene() -> SceneModel:
    bounds = {
        "min_xyz": state.sim.world.bounds.min_xyz,
        "max_xyz": state.sim.world.bounds.max_xyz,
    }
    obstacles = [
        {"center": o.center, "radius": o.radius} for o in state.sim.world.obstacles
    ]
    return SceneModel(bounds=bounds, obstacles=obstacles)


@app.get("/camera/frame")
async def get_camera_frame() -> Response:
    if state.latest_frame_jpeg is not None:
        return Response(content=state.latest_frame_jpeg, media_type="image/jpeg")
    if state.latest_frame is None:
        return Response(status_code=204)
    ok, encoded = cv2.imencode(".jpg", state.latest_frame)
    if not ok:
        return Response(status_code=500)
    jpeg = encoded.tobytes()
    state.latest_frame_jpeg = jpeg
    return Response(content=jpeg, media_type="image/jpeg")


@app.post("/scene")
async def set_scene(scene: SceneModel) -> Dict[str, str]:
    world = WorldState()
    world.bounds.min_xyz = scene.bounds.get("min_xyz", world.bounds.min_xyz)
    world.bounds.max_xyz = scene.bounds.get("max_xyz", world.bounds.max_xyz)
    world.obstacles = [
        SphereObstacle(center=o["center"], radius=o["radius"])
        for o in scene.obstacles
    ]
    state.sim.world = world
    return {"status": "updated"}


@app.post("/scene/save")
async def save_scene() -> Dict[str, str]:
    scene = await get_scene()
    state.scene_path.write_text(scene.json(), encoding="utf-8")
    return {"status": "saved", "path": str(state.scene_path)}


@app.post("/scene/load")
async def load_scene() -> Dict[str, str]:
    if not state.scene_path.exists():
        return {"status": "missing"}
    data = state.scene_path.read_text(encoding="utf-8")
    scene = SceneModel.parse_raw(data)
    await set_scene(scene)
    return {"status": "loaded"}


@app.post("/recordings/start")
async def start_recording() -> Dict[str, str]:
    state.recorder.start()
    return {"status": "recording"}


@app.post("/recordings/stop")
async def stop_recording() -> Dict[str, str]:
    state.recorder.stop()
    return {"status": "stopped"}


@app.post("/recordings/play")
async def play_recording() -> Dict[str, str]:
    state.recorder.start_playback()
    return {"status": "playback"}


@app.post("/recordings/clear")
async def clear_recording() -> Dict[str, str]:
    state.recorder.clear()
    return {"status": "cleared"}


@app.get("/recordings/status")
async def recording_status() -> Dict[str, Any]:
    return {
        "recording": state.recorder.recording,
        "playback": state.recorder.playback,
        "frames": len(state.recorder.frames),
    }


@app.post("/tests/start")
async def start_test(req: Optional[TestStartRequest] = None) -> Dict[str, Any]:
    _start_test(req)
    return state.test.to_dict(state.sim.time_s)


@app.post("/tests/stop")
async def stop_test() -> Dict[str, Any]:
    _stop_test()
    return state.test.to_dict(state.sim.time_s)


@app.get("/tests/status")
async def test_status() -> Dict[str, Any]:
    return state.test.to_dict(state.sim.time_s)


@app.post("/control/mode")
async def set_control_mode(req: ControlModeRequest) -> Dict[str, str]:
    mode = req.mode.lower().strip()
    if mode not in {"manual", "script", "rl"}:
        return {"status": "error", "message": "invalid mode"}
    state.control_mode = mode
    return {"status": "ok", "mode": state.control_mode}


@app.post("/rl/start")
async def start_rl() -> Dict[str, Any]:
    if state.rl_trainer is None:
        state.rl_trainer = RLTrainer(world=state.sim.world, camera=state.camera)
    state.rl_trainer.start()
    return state.rl_trainer.status.to_dict()


@app.post("/rl/stop")
async def stop_rl() -> Dict[str, Any]:
    if state.rl_trainer is None:
        return {"running": False}
    state.rl_trainer.stop()
    return state.rl_trainer.status.to_dict()


@app.get("/rl/status")
async def rl_status() -> Dict[str, Any]:
    if state.rl_trainer is None:
        return {"running": False}
    status = state.rl_trainer.status.to_dict()
    status["mode"] = state.control_mode
    return status


async def simulation_loop() -> None:
    tick = 0.02
    while True:
        if state.recorder.playback:
            telemetry = state.recorder.next_frame()
        else:
            script_command = state.script_host.pull_latest_command()
            if state.control_mode == "rl" and state.rl_trainer is not None:
                pre_frame = render_topdown(state.sim.drone, state.sim.world, state.camera)
                pre_vision = state.vision.process(pre_frame).to_dict()
                obs = build_observation(
                    state.sim, pre_vision, state.sim.world, state.rl_trainer.config
                )
                action = state.rl_trainer.policy.act(obs)
                state.sim.command = PolicyModel.action_to_command(
                    action, state.rl_trainer.config
                )
            elif state.control_mode == "script" and script_command is not None:
                state.sim.command = ControlCommand(**script_command)
            else:
                state.sim.command = state.manual_command

            state.sim.step(tick)
            telemetry = state.sim.drone.to_telemetry(state.sim.time_s)
            frame = render_topdown(state.sim.drone, state.sim.world, state.camera)
            state.latest_frame = frame
            ok, encoded = cv2.imencode(".jpg", frame)
            state.latest_frame_jpeg = encoded.tobytes() if ok else None
            vision = state.vision.process(frame)
            telemetry["vision"] = vision.to_dict()
            _update_test(telemetry)
            telemetry["test"] = state.test.to_dict(state.sim.time_s)
            if state.rl_trainer is not None:
                telemetry["rl"] = state.rl_trainer.status.to_dict()
                telemetry["rl"]["mode"] = state.control_mode
            state.script_host.push_telemetry(telemetry)
            state.recorder.add_frame(telemetry)

        if state.clients:
            dead_clients = []
            state.camera_seq += 1
            send_camera = (
                state.latest_frame_jpeg is not None
                and state.camera_seq % state.camera_send_stride == 0
            )
            camera_payload = None
            if send_camera:
                camera_payload = {
                    "type": "camera",
                    "jpeg": base64.b64encode(state.latest_frame_jpeg).decode("ascii"),
                }
            for client in state.clients:
                try:
                    await client.send_json({"type": "telemetry", **telemetry})
                    if camera_payload is not None:
                        await client.send_json(camera_payload)
                except Exception:
                    dead_clients.append(client)
            for client in dead_clients:
                state.clients.discard(client)

        await asyncio.sleep(tick)
