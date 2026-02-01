from __future__ import annotations

import asyncio
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Set

from fastapi import FastAPI, WebSocket, WebSocketDisconnect
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from .sim.core import SimCore
from .sim.drone import ControlCommand
from .sim.recording import Recorder
from .sim.world import SphereObstacle, WorldState
from .scripting.host import ScriptHost


class ScriptRunRequest(BaseModel):
    source: str


class SceneModel(BaseModel):
    bounds: Dict[str, List[float]]
    obstacles: List[Dict[str, Any]]


@dataclass
class AppState:
    sim: SimCore = field(default_factory=SimCore)
    script_host: ScriptHost = field(default_factory=ScriptHost)
    manual_command: ControlCommand = field(default_factory=ControlCommand)
    clients: Set[WebSocket] = field(default_factory=set)
    recorder: Recorder = field(default_factory=Recorder)
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


@app.on_event("startup")
async def _startup() -> None:
    state.sim.world = _build_default_world()
    asyncio.create_task(simulation_loop())


@app.on_event("shutdown")
async def _shutdown() -> None:
    state.script_host.stop()


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
    return {"status": "started"}


@app.post("/scripts/stop")
async def stop_script() -> Dict[str, str]:
    state.script_host.stop()
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


async def simulation_loop() -> None:
    tick = 0.02
    while True:
        if state.recorder.playback:
            telemetry = state.recorder.next_frame()
        else:
            script_command = state.script_host.pull_latest_command()
            if script_command is not None:
                state.sim.command = ControlCommand(**script_command)
            else:
                state.sim.command = state.manual_command

            state.sim.step(tick)
            telemetry = state.sim.drone.to_telemetry(state.sim.time_s)
            state.script_host.push_telemetry(telemetry)
            state.recorder.add_frame(telemetry)

        if state.clients:
            dead_clients = []
            for client in state.clients:
                try:
                    await client.send_json({"type": "telemetry", **telemetry})
                except Exception:
                    dead_clients.append(client)
            for client in dead_clients:
                state.clients.discard(client)

        await asyncio.sleep(tick)
