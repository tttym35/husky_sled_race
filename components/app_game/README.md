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


At 30 Hz, the model runs a touch-driven four-state machine with two steady states
(`APP_GAME_STATE_STOP`, `APP_GAME_STATE_STRAIGHT`) and two temporary turning states
(`APP_GAME_STATE_LEFT`, `APP_GAME_STATE_RIGHT`):

- Boot / reset starts in `STRAIGHT` at full speed (`speed = 1.0`) and activates
  a 3-pulse boot hint (`intro_hint_active` for 72 ticks, 24 ticks per pulse).
- `STRAIGHT`: swipe left -> `LEFT` (90 ticks / 3 s), swipe right -> `RIGHT`
  (90 ticks / 3 s), swipe down -> smooth brake to `STOP`.
- `LEFT`: expires after 90 ticks or cancels immediately on swipe right -> smooth
  return to `STRAIGHT`; swipe down is ignored.
- `RIGHT`: expires after 90 ticks or cancels immediately on swipe left -> smooth
  return to `STRAIGHT`; swipe down is ignored.
- `STOP`: swipe up or double-tap -> smooth accelerate to `STRAIGHT`; swipe left
  or right stays in `STOP` and pulses the top up-arrow hint 3 times (`up_hint_active`
  for 72 ticks) to cue swiping up; swipe down is ignored. Once fully stopped
  (`speed == 0`), `idle_tick` increments to drive the stationary tail-wag cycle.

Every accepted touch gesture dismisses any active boot hint and starts a 16-tick
direction feedback flash (`feedback_dir`, `feedback_remaining`). Distance and gait
integrate speed and freeze while stopped; bounded accumulators wrap at 1680 world
units and 480 gait ticks. Pause freezes ticks and gesture execution.

`app_game_pointer_event()` accepts tracked pointer/touch input (clamped to viewport)
and classifies swipes (>= 44 px) and double-taps (<= 28 px move, <= 12 ticks hold,
<= 15 ticks gap). `app_game_set_pointer()` forwards track 0. `app_game_set_control()`
remains reserved for external sub-board keys and IMU integration.
