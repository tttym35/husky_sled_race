"""Record and verify two complete demo cycles using the official shared C Host ABI."""

import importlib.util
import io
import json
from pathlib import Path
from PIL import Image

p = Path(__file__).resolve().parent.parent
engine = p.parents[1] / "submodule/raylib-lite-engine"
spec = importlib.util.spec_from_file_location("engine_host", engine / "host/run_game.py")
mod = importlib.util.module_from_spec(spec)
spec.loader.exec_module(mod)
rt = mod.GenericHostRuntime(p, p / "build-host", generation=20)
frames = []
checkpoints = []
states = []
previous = None
stationary = None
expected = ["straight", "left", "right", "straight_return", "stop"]
try:
    for tick in range(1, 1801):
        if tick == 20:
            rt.pointer(0, 15, 450, True)
            rt.action(3, True)
            rt.imu(0.8, -0.4, 1)
        rt.step(False, False, False)
        state = rt.metadata()
        cycle = tick % 900
        assert state["stage"] == expected[cycle // 180]
        assert state["dog_count"] == 6 and not state["pointer_down"]
        assert 0 <= state["speed"] <= 1 and -1 <= state["turn"] <= 1
        assert 0 <= state["powder_count"] <= 256
        if previous is not None:
            assert abs(state["turn"] - previous["turn"]) < 0.07
            assert abs(state["speed"] - previous["speed"]) < 0.04
        if 760 <= cycle < 900:
            assert state["speed"] == 0 and state["powder_count"] == 0
            if previous is not None:
                assert state["distance"] == previous["distance"]
                assert state["gait"] == previous["gait"]
        if tick in [790, 850]:
            raw, _, _ = rt.snapshot_rgb565()
            if stationary is None:
                stationary = raw
            else:
                assert raw == stationary, "Stopped scene must remain pixel-identical after powder fades"
        if tick <= 900 and tick % 6 == 0:
            frames.append(Image.open(io.BytesIO(rt.frame())).convert("RGB"))
        if tick in [120, 300, 480, 630, 720, 735, 790, 850, 1020]:
            im = Image.open(io.BytesIO(rt.frame())).convert("RGB")
            im.save(p / "test_artifacts" / f"cycle_frame_{tick:04}.png")
            checkpoints.append(im)
            states.append(state)
        if cycle in [120, 300, 480, 630]:
            assert state["powder_count"] > 0
        previous = state
    frames[0].save(
        p / "test_artifacts/state_cycle_preview.gif", save_all=True, append_images=frames[1:], duration=200, loop=0
    )
    contact = Image.new("RGB", (480 * 3, 480 * 3))
    for n, im in enumerate(checkpoints):
        contact.paste(im, ((n % 3) * 480, (n // 3) * 480))
    contact.save(p / "test_artifacts/cycle_contact.png")
    (p / "test_artifacts/cycle_check.json").write_text(json.dumps(states, indent=2))
    print(
        "PASS: two complete cycles; stage order; continuous turn/speed; six dogs; ignored input; powder emitted while running; zero powder and pixel-identical scene after stopping; restart."
    )
finally:
    rt.close()
