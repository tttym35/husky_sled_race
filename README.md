# husky_sled_race

An autonomous five-stage six-husky sledding visual prototype for ESP-Mosaico (480×480).
Three pairs of dogs run continuously through a blue-hour snowy forest. Eight
forward-facing gait frames, perspective ground, passing trees and lamps, towlines,
powder and a sled handle share one native C renderer on Host and device.
The 30-second loop is straight (6 s), left (6 s), right (6 s), straight (6 s),
then stopped (6 s). Turns and speed ease between states; the last straight slows
to a halt. Snow powder and small flakes emit from all six dogs' rear paws while
running, disperse within 34 ticks after emission ends, and remain absent during
the stop. Ground, trees, lamps and gait stop together. Existing dog frames are
reused, with frame 7 held at rest. No standing animation has been added.

The background plate contains only sky and snow. Trees and lamps are independent
moving sprites. A shared road curve positions the ruts, props and team using the
same artwork throughout. Touch and action inputs are intentionally ignored.
There is no scoring, lap ending, audio or IMU control in this visual prototype.

From the workspace root:

```sh
python3 projects/husky_sled_race/assets_src/prepare_art.py
python3 mosaico.py game sim --project projects/husky_sled_race
python3 mosaico.py game sim --project projects/husky_sled_race --headless --frames 120
python3 mosaico.py game build --project projects/husky_sled_race
python3 mosaico.py iris system-update --project projects/husky_sled_race
```

Use the workspace-pinned ESP-IDF environment for builds and its documented
simulator/compiler setup. Source artwork and reproducible RGB565 packing are in
`assets_src/`; generated immutable data is in the runtime component. The user-
approved review artwork is in `assets/review/2026_11_19/`. `test_artifacts/state_cycle_preview.gif` records one complete loop.
`test_artifacts/check_animation.py` verifies two cycles including stable stop frames.
`test_artifacts/` holds
simulator frames, recordings, build logs and live-device evidence.

The app preserves the existing retained Vibe Mode partition prefix. Installation
and device diagnostics use only the workspace `mosaico.py` entry point.
