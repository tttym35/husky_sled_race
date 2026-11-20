# husky_sled_race

A touch-controlled six-husky sledding game prototype for ESP-Mosaico (480×480
round display). Three pairs of dogs run through a blue-hour snowy forest. Eight
forward-facing gait frames, seven stationary tail-wag frames, perspective
ground, passing trees and lamps, towlines, powder, a sled handle and translucent
pure-icon touch cues share one native C renderer on Host and device.

## Controls (v1.1.0)

- **Boot state**: Starts directly in `STRAIGHT` running mode. Left, right and
  down white translucent double-chevron hints pulse 3 times and fade out.
- **Steady states**: `STRAIGHT` (running) and `STOP` (stationary 7-frame tail
  wag).
- **Temporary turns**: `LEFT` and `RIGHT` each hold for 3 s (90 ticks @ 30 Hz)
  and then ease smoothly back to `STRAIGHT`.
- **Gestures**:
  - In `STRAIGHT`: swipe left -> `LEFT` (3 s), swipe right -> `RIGHT` (3 s),
    swipe down -> smooth brake to `STOP`.
  - In `LEFT` / `RIGHT`: swipe back toward center (`LEFT` + swipe right, or
    `RIGHT` + swipe left) -> ease immediately back to `STRAIGHT`; swipe down is
    ignored.
  - In `STOP`: swipe up or double-tap -> accelerate into `STRAIGHT`; swipe left
    or right stays stopped and pulses the top up-arrow hint 3 times to prompt
    swiping up; swipe down is ignored.
- **Feedback**: Every executed touch gesture flashes its matching white
  translucent direction icon once.

## Next Release Roadmap / 下一版规划

- 下一版增添传感器子板、摄像头等丰富功能，雪橇赛地图，音乐音效反馈。
- Planned additions for the next release: sensor sub-board and camera
  integrations, sled race track/map, and background music with sound effects
  feedback.

## Build and Verification

From the workspace root:

```sh
python3 projects/husky_sled_race/assets_src/prepare_art.py
python3 mosaico.py game sim --project projects/husky_sled_race
python3 mosaico.py game sim --project projects/husky_sled_race --headless --frames 90
python3 mosaico.py game build --project projects/husky_sled_race
python3 mosaico.py iris system-update --project projects/husky_sled_race
```

Use the workspace-pinned ESP-IDF environment for builds and its documented
simulator/compiler setup. Source artwork and reproducible RGB565 packing are in
`assets_src/`; generated immutable data is in the runtime component. Approved
review artwork is in `assets/review/2026_11_19/` and `assets/review/2026_11_20/`.
`test_artifacts/check_animation.py` verifies the touch state machine, gestures,
smooth transitions, tail wag and icon cues on the Host ABI. `test_artifacts/`
holds simulator frames, recordings, build logs and live-device evidence.

The app preserves the existing retained Vibe Mode partition prefix. Installation
and device diagnostics use only the workspace `mosaico.py` entry point.
