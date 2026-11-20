// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdbool.h>
#include <stdint.h>

#ifdef __cplusplus
extern "C" {
#endif

/** Opaque model owned by one loop; no concurrent or ISR access.
 * Lifecycle and timing contracts: ../README.md. */
typedef struct app_game *app_game_handle_t;

typedef enum {
    APP_GAME_OK = 0,
    APP_GAME_INVALID_ARGUMENT,
    APP_GAME_NO_MEMORY,
} app_game_err_t;

typedef struct {
    uint16_t width;    /**< Viewport width in pixels, 1..65535. */
    uint16_t height;   /**< Viewport height in pixels, 1..65535. */
} app_game_config_t;

typedef enum {
    APP_DEMO_STRAIGHT,
    APP_DEMO_LEFT,
    APP_DEMO_RIGHT,
    APP_DEMO_STRAIGHT_RETURN,
    APP_DEMO_STOP,
} app_demo_stage_t;

enum { APP_DEMO_STAGE_TICKS = 180, APP_DEMO_CYCLE_TICKS = 900 };

/** Player control, reserved for the interactive version (sub-board keys / IMU).
 * Stored by app_game_set_control(); the autonomous demo cycle ignores it. */
typedef struct {
    float steer;  /**< -1 full left .. +1 full right. */
    bool brake;
    bool jump;
} app_game_control_t;

typedef struct {
    uint32_t tick;       /**< Update count, wraps modulo 2^32; not milliseconds. */
    int32_t pointer_x;   /**< Pixels from left edge, 0..width-1. */
    int32_t pointer_y;   /**< Pixels from top edge, 0..height-1. */
    bool pointer_down;
    bool paused;
    app_demo_stage_t stage;
    uint32_t cycle_tick; /**< 30-second demo cycle, 0..899 at 30 Hz. */
    float speed;        /**< Normalized travel/gait speed, 0..1. */
    float turn;         /**< Smooth left (-1) / straight (0) / right (+1). */
    float distance;     /**< Integrated world travel, wraps at 1680 units. */
    float gait;         /**< Integrated animation ticks, wraps at 480. */
    app_game_control_t control; /**< Last control received; not yet applied. */
} app_game_snapshot_t;

/** Copy config and create a caller-owned model; arguments must be non-NULL.
 * Width/height must be positive; clears *out_handle on failure.
 * Returns APP_GAME_OK, APP_GAME_INVALID_ARGUMENT or APP_GAME_NO_MEMORY. */
app_game_err_t app_game_create(const app_game_config_t *config, app_game_handle_t *out_handle);

/** Free the model and clear the handle; borrowed copies become invalid.
 * NULL pointer/handle is a no-op. */
void app_game_destroy(app_game_handle_t *handle);

/** Reset input, tick and pause state to zero; keep viewport. NULL is a no-op. */
void app_game_reset(app_game_handle_t handle);
/** Change pause state. NULL is a no-op. Pausing stops ticks, not input recording. */
void app_game_set_paused(app_game_handle_t handle, bool paused);
/** Set pointer coordinates in pixels (clamped to viewport) and button state.
 * NULL handle is a no-op. */
void app_game_set_pointer(app_game_handle_t handle, int32_t x, int32_t y, bool pressed);
/** Store player control (clamped) for the next version's steering; the current
 * autonomous cycle does not read it. NULL handle or control is a no-op. */
void app_game_set_control(app_game_handle_t handle, const app_game_control_t *control);
/** Advance one fixed tick unless paused; the caller supplies cadence (default 30 Hz).
 * NULL handle is a no-op; no rendering or hardware access. */
void app_game_update(app_game_handle_t handle);
/** Return a value snapshot on the owning loop; NULL returns all zeros. */
app_game_snapshot_t app_game_read(app_game_handle_t handle);

#ifdef __cplusplus
}
#endif
