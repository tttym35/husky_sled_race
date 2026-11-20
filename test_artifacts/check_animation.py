"""Verify touch control state machine, gestures, smooth motion, and icon cues via Host ABI."""

import importlib.util
import io
import json
from pathlib import Path
from PIL import Image

PROJECT = Path(__file__).resolve().parent.parent
ENGINE = PROJECT.parents[1] / "submodule/raylib-lite-engine"
SPEC = importlib.util.spec_from_file_location("engine_host", ENGINE / "host/run_game.py")
MOD = importlib.util.module_from_spec(SPEC)
SPEC.loader.exec_module(MOD)


def step_n(rt, count, previous=None):
    state = previous
    for _ in range(count):
        rt.step(False, False, False)
        cur = rt.metadata()
        assert cur["mode"] == "touch" and cur["dog_count"] == 6
        assert 0.0 <= cur["speed"] <= 1.0 and -1.0 <= cur["turn"] <= 1.0
        assert 0 <= cur["powder_count"] <= 256
        if state is not None:
            assert abs(cur["turn"] - state["turn"]) < 0.08, (state["turn"], cur["turn"])
            assert abs(cur["speed"] - state["speed"]) < 0.06, (state["speed"], cur["speed"])
        state = cur
    return state


def do_swipe(rt, x0, y0, x1, y1, track_id=0):
    rt.pointer(track_id, x0, y0, True)
    rt.step(False, False, False)
    rt.pointer(track_id, (x0 + x1) // 2, (y0 + y1) // 2, True)
    rt.step(False, False, False)
    rt.pointer(track_id, x1, y1, True)
    rt.step(False, False, False)
    rt.pointer(track_id, x1, y1, False)
    rt.step(False, False, False)
    return rt.metadata()


def do_tap(rt, x, y, hold_ticks=1, track_id=0):
    rt.pointer(track_id, x, y, True)
    for _ in range(hold_ticks):
        rt.step(False, False, False)
    rt.pointer(track_id, x + 3, y - 2, False)
    rt.step(False, False, False)
    return rt.metadata()


def snap(rt, name, checkpoints, states):
    im = Image.open(io.BytesIO(rt.frame())).convert("RGB")
    im.save(PROJECT / "test_artifacts" / name)
    checkpoints.append(im)
    states.append({"name": name, **rt.metadata()})
    return im


def region_luma(im, cx, cy, half=20):
    crop = im.crop((cx - half, cy - half, cx + half, cy + half)).convert("L")
    data = list(crop.get_flattened_data())
    return sum(data) / len(data)


def main():
    rt = MOD.GenericHostRuntime(PROJECT, PROJECT / "build-host", generation=21)
    checkpoints = []
    states = []
    try:
        # 1. Boot straight running with 3-pulse intro hints (left/right/down)
        st = step_n(rt, 12)
        assert st["state"] == "straight"
        assert st["speed"] == 1.0 and st["turn"] == 0.0
        assert st["intro_hint_active"] is True
        intro_peak = snap(rt, "touch_01_intro_hint.png", checkpoints, states)

        # Wait until intro hints finish (72 ticks total)
        st = step_n(rt, 65, st)
        assert st["intro_hint_active"] is False
        assert st["state"] == "straight" and st["speed"] == 1.0
        after_intro = Image.open(io.BytesIO(rt.frame())).convert("RGB")
        # Intro peak should visibly brighten left/right/down cue regions
        assert region_luma(intro_peak, 64, 240) > region_luma(after_intro, 64, 240) + 1.5
        assert region_luma(intro_peak, 416, 240) > region_luma(after_intro, 416, 240) + 1.5
        assert region_luma(intro_peak, 240, 416) > region_luma(after_intro, 240, 416) + 1.5

        # Ignored gestures in STRAIGHT: swipe up & double tap
        st = do_swipe(rt, 240, 320, 240, 180)
        assert st["state"] == "straight" and st["feedback_dir"] == "none"
        do_tap(rt, 240, 240)
        step_n(rt, 3, st)
        st = do_tap(rt, 240, 240)
        assert st["state"] == "straight" and st["feedback_dir"] == "none"

        # 2. STRAIGHT -> swipe left -> LEFT (3s auto return)
        st = do_swipe(rt, 300, 240, 180, 240)
        assert st["state"] == "left" and st["feedback_dir"] == "left"
        assert st["feedback_remaining"] > 0 and st["turn_remaining"] > 80
        snap(rt, "touch_02_swipe_left_feedback.png", checkpoints, states)

        # Ignored gestures during LEFT: swipe down & swipe left
        rem_before = st["turn_remaining"]
        st = do_swipe(rt, 240, 180, 240, 320)
        assert st["state"] == "left" and st["turn_remaining"] < rem_before
        assert st["feedback_dir"] != "down"
        st = do_swipe(rt, 300, 240, 180, 240)
        assert st["state"] == "left"

        # Mid-turn peak frame
        st = step_n(rt, 25, st)
        assert st["state"] == "left" and st["turn"] < -0.95
        snap(rt, "touch_03_turn_left_peak.png", checkpoints, states)

        # Let remaining 3s countdown expire -> smooth auto-return without feedback icon
        st = step_n(rt, 65, st)
        assert st["state"] == "straight" and st["turn_remaining"] == 0
        assert st["feedback_dir"] == "none"
        st = step_n(rt, 35, st)
        assert abs(st["turn"]) < 0.001

        # 3. STRAIGHT -> swipe right -> RIGHT -> cancel early with swipe left
        st = do_swipe(rt, 180, 240, 300, 240)
        assert st["state"] == "right" and st["feedback_dir"] == "right"
        snap(rt, "touch_04_swipe_right_feedback.png", checkpoints, states)

        # Swipe down ignored during RIGHT
        st = do_swipe(rt, 240, 180, 240, 320)
        assert st["state"] == "right" and st["feedback_dir"] != "down"

        st = step_n(rt, 24, st)
        assert st["state"] == "right" and st["turn"] > 0.85

        # Swipe left (counter-swipe) cancels RIGHT -> STRAIGHT with left feedback flash
        st = do_swipe(rt, 300, 240, 180, 240)
        assert st["state"] == "straight" and st["turn_remaining"] == 0
        assert st["feedback_dir"] == "left" and st["feedback_remaining"] > 0
        snap(rt, "touch_05_cancel_right_with_left.png", checkpoints, states)
        st = step_n(rt, 35, st)
        assert abs(st["turn"]) < 0.001

        # 4. STRAIGHT -> swipe down -> smooth brake to STOP with tail wag
        st = do_swipe(rt, 240, 180, 240, 320)
        assert st["state"] == "stop" and st["feedback_dir"] == "down"
        assert st["speed"] > 0.5  # still smoothly braking
        snap(rt, "touch_06_swipe_down_feedback.png", checkpoints, states)

        st = step_n(rt, 80, st)
        assert st["state"] == "stop" and st["speed"] == 0.0 and st["powder_count"] == 0
        dist_frozen = st["distance"]
        gait_frozen = st["gait"]
        raw_a, _, _ = rt.snapshot_rgb565()
        snap(rt, "touch_07_stopped_wag.png", checkpoints, states)
        st = step_n(rt, 12, st)
        assert st["distance"] == dist_frozen and st["gait"] == gait_frozen
        assert st["idle_tick"] > 0
        raw_b, _, _ = rt.snapshot_rgb565()
        assert raw_a != raw_b, "Stopped team should keep wagging tails"

        # 5. In STOP: swipe down & single tap do nothing; swipe left/right stays stopped
        #    and pulses top up-arrow 3 times (72 ticks) to prompt swiping up
        st = do_swipe(rt, 240, 180, 240, 320)
        assert st["state"] == "stop" and st["speed"] == 0.0
        assert st["feedback_dir"] == "none" and st["up_hint_active"] is False
        st = do_tap(rt, 240, 240)
        st = step_n(rt, 20, st)
        assert st["state"] == "stop" and st["speed"] == 0.0 and st["up_hint_active"] is False

        # Swipe left in STOP -> still stopped, top up-arrow pulses 3 times then disappears
        st = do_swipe(rt, 300, 240, 180, 240)
        assert st["state"] == "stop" and st["speed"] == 0.0
        assert st["feedback_dir"] == "none" and st["up_hint_active"] is True
        st = step_n(rt, 10, st)
        up_hint_peak = Image.open(io.BytesIO(rt.frame())).convert("RGB")
        st = step_n(rt, 65, st)
        assert st["state"] == "stop" and st["up_hint_active"] is False
        up_hint_gone = Image.open(io.BytesIO(rt.frame())).convert("RGB")
        assert region_luma(up_hint_peak, 240, 64) > region_luma(up_hint_gone, 240, 64) + 1.5

        # Swipe right in STOP -> triggers 3-pulse up hint again; swipe up dismisses it and starts
        st = do_swipe(rt, 180, 240, 300, 240)
        assert st["state"] == "stop" and st["up_hint_active"] is True
        st = do_swipe(rt, 240, 320, 240, 180)
        assert st["state"] == "straight" and st["up_hint_active"] is False
        assert st["feedback_dir"] == "up"
        snap(rt, "touch_08_swipe_up_start.png", checkpoints, states)
        st = step_n(rt, 35, st)
        assert st["state"] == "straight" and st["speed"] == 1.0

        # 6. Brake to STOP, then double-tap -> accelerate to STRAIGHT with UP feedback
        st = do_swipe(rt, 240, 180, 240, 320)
        st = step_n(rt, 50, st)
        assert st["state"] == "stop" and st["speed"] == 0.0
        do_tap(rt, 220, 260)
        step_n(rt, 4, st)
        st = do_tap(rt, 235, 255)
        assert st["state"] == "straight" and st["feedback_dir"] == "up"
        snap(rt, "touch_09_double_tap_start.png", checkpoints, states)
        st = step_n(rt, 35, st)
        assert st["state"] == "straight" and st["speed"] == 1.0

        # 7. Intro hint dismissed immediately when an early valid gesture fires
        rt.control(3)  # RAYLIB_LITE_GAME_CONTROL_RESET
        st = step_n(rt, 6)
        assert st["intro_hint_active"] is True
        st = do_swipe(rt, 300, 240, 180, 240)
        assert st["state"] == "left" and st["intro_hint_active"] is False
        assert st["feedback_dir"] == "left"

        contact = Image.new("RGB", (480 * 3, 480 * 3))
        for idx, im in enumerate(checkpoints):
            contact.paste(im, ((idx % 3) * 480, (idx // 3) * 480))
        contact.save(PROJECT / "test_artifacts/touch_contact.png")
        (PROJECT / "test_artifacts/touch_check.json").write_text(json.dumps(states, indent=2))
        print(
            "PASS: boot straight + 3-pulse intro hints; left/right 3s turn & counter-swipe cancel; "
            "down smooth stop + wag; stop swipe-up & double-tap restart; invalid gestures ignored."
        )
    finally:
        rt.close()


if __name__ == "__main__":
    main()
