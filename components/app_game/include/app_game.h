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
    APP_GAME_STATE_STOP = 0,
    APP_GAME_STATE_STRAIGHT,
    APP_GAME_STATE_LEFT,
    APP_GAME_STATE_RIGHT,
} app_game_state_t;

typedef enum {
    APP_GAME_DIR_NONE = 0,
    APP_GAME_DIR_UP,
    APP_GAME_DIR_DOWN,
    APP_GAME_DIR_LEFT,
    APP_GAME_DIR_RIGHT,
} app_game_dir_t;

enum {
    APP_GAME_TURN_DURATION_TICKS = 90,   /**< 3 s @ 30 Hz before returning to STRAIGHT. */
    APP_GAME_INTRO_HINT_PULSES = 3,      /**< Boot hint flashes 3 times then hides. */
    APP_GAME_INTRO_PULSE_TICKS = 24,     /**< 0.8 s per pulse @ 30 Hz. */
    APP_GAME_INTRO_HINT_TICKS = APP_GAME_INTRO_HINT_PULSES * APP_GAME_INTRO_PULSE_TICKS,
    APP_GAME_FEEDBACK_TICKS = 16,        /**< ~0.53 s single flash for valid gestures. */
};

/** Player control, reserved for external sub-board keys / IMU integration.
 * Stored by app_game_set_control(); touch gestures drive the active state machine. */
typedef struct {
    float steer;  /**< -1 full left .. +1 full right. */
    bool brake;
    bool jump;
} app_game_control_t;

typedef struct {
    uint32_t tick;                 /**< Update count, wraps modulo 2^32; not milliseconds. */
    int32_t pointer_x;             /**< Pixels from left edge, 0..width-1. */
    int32_t pointer_y;             /**< Pixels from top edge, 0..height-1. */
    bool pointer_down;
    bool paused;
    app_game_state_t state;        /**< Active driving state (STOP/STRAIGHT/LEFT/RIGHT). */
    uint32_t turn_remaining;       /**< Ticks remaining in LEFT/RIGHT, 0..90. */
    uint32_t idle_tick;            /**< Monotonic ticks at full stop; drives tail wag. */
    float speed;                   /**< Normalized travel/gait speed, 0..1. */
    float turn;                    /**< Smooth left (-1) / straight (0) / right (+1). */
    float distance;                /**< Integrated world travel, wraps at 1680 units. */
    float gait;                    /**< Integrated animation ticks, wraps at 480. */
    uint32_t intro_hint_tick;      /**< Elapsed ticks in boot hint pulse, 0..72. */
    bool intro_hint_active;        /**< True while left/right/down boot hints pulse. */
    uint32_t up_hint_tick;         /**< Elapsed ticks in STOP swipe-up hint pulse, 0..72. */
    bool up_hint_active;           /**< True while top swipe-up hint pulses 3 times in STOP. */
    app_game_dir_t feedback_dir;   /**< Direction icon for latest executed gesture. */
    uint32_t feedback_remaining;   /**< Remaining ticks for gesture feedback flash. */
    app_game_control_t control;    /**< Last external control received. */
} app_game_snapshot_t;

/** Copy config and create a caller-owned model; arguments must be non-NULL.
 * Width/height must be positive; clears *out_handle on failure.
 * Returns APP_GAME_OK, APP_GAME_INVALID_ARGUMENT or APP_GAME_NO_MEMORY. */
app_game_err_t app_game_create(const app_game_config_t *config, app_game_handle_t *out_handle);

/** Free the model and clear the handle; borrowed copies become invalid.
 * NULL pointer/handle is a no-op. */
void app_game_destroy(app_game_handle_t *handle);

/** Reset to initial STRAIGHT running state with boot hints; keep viewport. NULL is a no-op. */
void app_game_reset(app_game_handle_t handle);
/** Change pause state. NULL is a no-op. Pausing stops ticks and gesture execution. */
void app_game_set_paused(app_game_handle_t handle, bool paused);
/** Feed a tracked pointer/touch event (clamped to viewport) into the gesture recognizer.
 * NULL handle is a no-op. */
void app_game_pointer_event(app_game_handle_t handle, int32_t track_id,
                            int32_t x, int32_t y, bool pressed);
/** Single-pointer convenience wrapper around app_game_pointer_event(..., track_id=0).
 * NULL handle is a no-op. */
void app_game_set_pointer(app_game_handle_t handle, int32_t x, int32_t y, bool pressed);
/** Store external player control (clamped) for future sub-board/IMU adapters.
 * NULL handle or control is a no-op. */
void app_game_set_control(app_game_handle_t handle, const app_game_control_t *control);
/** Advance one fixed tick unless paused; the caller supplies cadence (default 30 Hz).
 * NULL handle is a no-op; no rendering or hardware access. */
void app_game_update(app_game_handle_t handle);
/** Return a value snapshot on the owning loop; NULL returns all zeros. */
app_game_snapshot_t app_game_read(app_game_handle_t handle);

#ifdef __cplusplus
}
#endif
