# app_game

Owns viewport configuration, pointer state, pause/reset and fixed-step game rules.
It is pure C with no Engine, RTOS, display or other application dependency.
The private instance is defined only in `app_game.c`; `include/app_game.h` exports
an opaque handle, configuration values and value snapshots.

```c
app_game_handle_t game = NULL;
const app_game_config_t config = {480, 480}; /* pixels */
if (app_game_create(&config, &game) == APP_GAME_OK) {
    app_game_set_pointer(game, 20, 30, true);
    app_game_update(game); /* one fixed tick, not elapsed milliseconds */
    app_game_snapshot_t snapshot = app_game_read(game);
    (void)snapshot;
    app_game_destroy(&game);
}
```

The creator owns the handle and serializes every call on one loop. Config is
copied, snapshots contain no owned pointers, destroy clears the owner handle.
Destroy before reusing an owned handle slot; callbacks must not retain freed handles.
Calls are synchronous, with no locks, waits or deadlines; only create/destroy use
the allocator. Other operations perform bounded in-memory work. Creation reports
invalid arguments or allocation failure; harmless NULL behavior for other
operations is documented in the public header. Ticks wrap modulo 2^32; viewport
coordinates are pixels and are clamped.

Add gameplay here; adapters translate input into these public calls. Rendering
reads snapshots and must not reach into the private struct. Test game rules with
a native C compiler without firmware or graphics dependencies.


At 30 Hz, the model cycles through five 180-tick stages: straight, left, right,
straight return, stopped. A 45-tick smoothstep controls turn changes, start and
braking. Distance and gait integrate speed and freeze while stopped. Bounded
accumulators wrap at 1680 world units (a multiple of roadside spacing/pattern) and 480 gait ticks. `cycle_tick` advances independently
of wrapping `tick`. Snapshot fields expose stage, speed, curvature and travel to
the renderer and Host diagnostics. Pause freezes all model updates.

`app_game_set_control()` is the reserved entry point for the interactive version:
it stores steer (-1..1), brake and jump in the snapshot. The autonomous cycle does
not read it yet; adapters for sub-board keys and IMU will call it.
