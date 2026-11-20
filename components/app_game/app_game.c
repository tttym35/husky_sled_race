// SPDX-License-Identifier: Apache-2.0
#include <math.h>
#include <stdlib.h>
#include "include/app_game.h"

enum {
    SWIPE_MIN_PX = 44,
    TAP_MAX_MOVE_PX = 28,
    TAP_MAX_HOLD_TICKS = 12,        /* 0.40 s @ 30 Hz */
    DOUBLE_TAP_MAX_GAP_TICKS = 15,  /* 0.50 s @ 30 Hz */
    SPEED_ACCEL_TICKS = 30,         /* 1.00 s stop -> full speed */
    SPEED_BRAKE_TICKS = 40,         /* 1.33 s full speed -> stop */
    TURN_TRANSITION_TICKS = 30,     /* 1.00 s for full 0 <-> 1 turn */
    TURN_MIN_TRANSITION_TICKS = 10, /* 0.33 s minimum smooth return */
};

typedef enum {
    GESTURE_NONE = 0,
    GESTURE_SWIPE_UP,
    GESTURE_SWIPE_DOWN,
    GESTURE_SWIPE_LEFT,
    GESTURE_SWIPE_RIGHT,
    GESTURE_DOUBLE_TAP,
} app_gesture_t;

struct app_game {
    app_game_config_t config;
    app_game_snapshot_t state;
    float speed_ramp;
    float turn_from;
    float turn_to;
    float turn_t;
    float turn_step;
    uint8_t contact_mask;
    bool touch_active;
    int32_t active_track;
    int32_t start_x;
    int32_t start_y;
    int32_t last_x;
    int32_t last_y;
    int32_t max_dist_sq;
    uint32_t press_tick;
    bool swipe_triggered;
    bool tap_pending;
    uint32_t last_tap_tick;
};

static float smoothstep(float t)
{
    if (t <= 0.0f) {
        return 0.0f;
    }
    if (t >= 1.0f) {
        return 1.0f;
    }
    return t * t * (3.0f - 2.0f * t);
}

static void start_turn_transition(app_game_handle_t game, float target)
{
    game->turn_from = game->state.turn;
    game->turn_to = target;
    float delta = fabsf(target - game->turn_from);
    if (delta < 0.0001f) {
        game->turn_t = 1.0f;
        game->turn_step = 1.0f;
        game->state.turn = target;
        return;
    }
    float duration = delta * (float)TURN_TRANSITION_TICKS;
    if (duration < (float)TURN_MIN_TRANSITION_TICKS) {
        duration = (float)TURN_MIN_TRANSITION_TICKS;
    }
    game->turn_t = 0.0f;
    game->turn_step = 1.0f / duration;
}

static void reset_model(app_game_handle_t game)
{
    game->state = (app_game_snapshot_t) {
        .state = APP_GAME_STATE_STRAIGHT,
        .speed = 1.0f,
        .intro_hint_active = true,
    };
    game->speed_ramp = 1.0f;
    game->turn_from = 0.0f;
    game->turn_to = 0.0f;
    game->turn_t = 1.0f;
    game->turn_step = 1.0f;
    game->contact_mask = 0;
    game->touch_active = false;
    game->active_track = 0;
    game->start_x = 0;
    game->start_y = 0;
    game->last_x = 0;
    game->last_y = 0;
    game->max_dist_sq = 0;
    game->press_tick = 0;
    game->swipe_triggered = false;
    game->tap_pending = false;
    game->last_tap_tick = 0;
}

static void trigger_feedback(app_game_handle_t game, app_game_dir_t dir)
{
    game->state.intro_hint_active = false;
    game->state.up_hint_active = false;
    game->state.feedback_dir = dir;
    game->state.feedback_remaining = APP_GAME_FEEDBACK_TICKS;
}

static void apply_gesture(app_game_handle_t game, app_gesture_t gesture)
{
    app_game_snapshot_t *state = &game->state;
    switch (state->state) {
    case APP_GAME_STATE_STOP:
        if (gesture == GESTURE_SWIPE_UP || gesture == GESTURE_DOUBLE_TAP) {
            state->state = APP_GAME_STATE_STRAIGHT;
            state->turn_remaining = 0;
            start_turn_transition(game, 0.0f);
            trigger_feedback(game, APP_GAME_DIR_UP);
        } else if (gesture == GESTURE_SWIPE_LEFT || gesture == GESTURE_SWIPE_RIGHT) {
            state->up_hint_active = true;
            state->up_hint_tick = 0;
        }
        break;
    case APP_GAME_STATE_STRAIGHT:
        if (gesture == GESTURE_SWIPE_LEFT) {
            state->state = APP_GAME_STATE_LEFT;
            state->turn_remaining = APP_GAME_TURN_DURATION_TICKS;
            start_turn_transition(game, -1.0f);
            trigger_feedback(game, APP_GAME_DIR_LEFT);
        } else if (gesture == GESTURE_SWIPE_RIGHT) {
            state->state = APP_GAME_STATE_RIGHT;
            state->turn_remaining = APP_GAME_TURN_DURATION_TICKS;
            start_turn_transition(game, 1.0f);
            trigger_feedback(game, APP_GAME_DIR_RIGHT);
        } else if (gesture == GESTURE_SWIPE_DOWN) {
            state->state = APP_GAME_STATE_STOP;
            state->turn_remaining = 0;
            start_turn_transition(game, 0.0f);
            trigger_feedback(game, APP_GAME_DIR_DOWN);
        }
        break;
    case APP_GAME_STATE_LEFT:
        if (gesture == GESTURE_SWIPE_RIGHT) {
            state->state = APP_GAME_STATE_STRAIGHT;
            state->turn_remaining = 0;
            start_turn_transition(game, 0.0f);
            trigger_feedback(game, APP_GAME_DIR_RIGHT);
        }
        break;
    case APP_GAME_STATE_RIGHT:
        if (gesture == GESTURE_SWIPE_LEFT) {
            state->state = APP_GAME_STATE_STRAIGHT;
            state->turn_remaining = 0;
            start_turn_transition(game, 0.0f);
            trigger_feedback(game, APP_GAME_DIR_LEFT);
        }
        break;
    }
}

static app_gesture_t classify_swipe(int32_t dx, int32_t dy, bool strict_axis)
{
    int32_t adx = dx < 0 ? -dx : dx;
    int32_t ady = dy < 0 ? -dy : dy;
    if (adx < SWIPE_MIN_PX && ady < SWIPE_MIN_PX) {
        return GESTURE_NONE;
    }
    if (strict_axis) {
        if (adx >= SWIPE_MIN_PX && adx * 4 >= ady * 5) {
            return dx < 0 ? GESTURE_SWIPE_LEFT : GESTURE_SWIPE_RIGHT;
        }
        if (ady >= SWIPE_MIN_PX && ady * 4 >= adx * 5) {
            return dy < 0 ? GESTURE_SWIPE_UP : GESTURE_SWIPE_DOWN;
        }
        return GESTURE_NONE;
    }
    if (adx >= ady) {
        return dx < 0 ? GESTURE_SWIPE_LEFT : GESTURE_SWIPE_RIGHT;
    }
    return dy < 0 ? GESTURE_SWIPE_UP : GESTURE_SWIPE_DOWN;
}

app_game_err_t app_game_create(const app_game_config_t *config, app_game_handle_t *ret_handle)
{
    if (!ret_handle) {
        return APP_GAME_INVALID_ARGUMENT;
    }
    *ret_handle = NULL;
    if (!config || !config->width || !config->height) {
        return APP_GAME_INVALID_ARGUMENT;
    }
    app_game_handle_t game = calloc(1, sizeof(*game));
    if (!game) {
        return APP_GAME_NO_MEMORY;
    }
    game->config = *config;
    reset_model(game);
    *ret_handle = game;
    return APP_GAME_OK;
}

void app_game_destroy(app_game_handle_t *handle)
{
    if (handle) {
        free(*handle);
        *handle = NULL;
    }
}

void app_game_reset(app_game_handle_t game)
{
    if (game) {
        reset_model(game);
    }
}

void app_game_set_paused(app_game_handle_t game, bool paused)
{
    if (game) {
        game->state.paused = paused;
        if (paused) {
            game->touch_active = false;
            game->contact_mask = 0;
            game->tap_pending = false;
            game->state.pointer_down = false;
        }
    }
}

void app_game_pointer_event(app_game_handle_t game, int32_t track_id,
                            int32_t x, int32_t y, bool pressed)
{
    if (!game) {
        return;
    }
    int32_t cx = x < 0 ? 0 : (x >= game->config.width ? game->config.width - 1 : x);
    int32_t cy = y < 0 ? 0 : (y >= game->config.height ? game->config.height - 1 : y);
    int32_t slot = (track_id >= 0 && track_id < 8) ? track_id : 0;
    uint8_t bit = (uint8_t)(1U << slot);
    if (pressed) {
        game->contact_mask |= bit;
    } else {
        game->contact_mask = (uint8_t)(game->contact_mask & (uint8_t)~bit);
    }
    game->state.pointer_x = cx;
    game->state.pointer_y = cy;
    game->state.pointer_down = game->contact_mask != 0;

    if (game->state.paused) {
        return;
    }

    if (pressed) {
        if (!game->touch_active) {
            game->touch_active = true;
            game->active_track = track_id;
            game->start_x = cx;
            game->start_y = cy;
            game->last_x = cx;
            game->last_y = cy;
            game->max_dist_sq = 0;
            game->press_tick = game->state.tick;
            game->swipe_triggered = false;
        } else if (track_id == game->active_track) {
            game->last_x = cx;
            game->last_y = cy;
            int32_t dx = cx - game->start_x;
            int32_t dy = cy - game->start_y;
            int32_t dist_sq = dx * dx + dy * dy;
            if (dist_sq > game->max_dist_sq) {
                game->max_dist_sq = dist_sq;
            }
            if (!game->swipe_triggered) {
                app_gesture_t swipe = classify_swipe(dx, dy, true);
                if (swipe != GESTURE_NONE) {
                    game->swipe_triggered = true;
                    game->tap_pending = false;
                    apply_gesture(game, swipe);
                }
            }
        }
        return;
    }

    /* Release: finish tracking if our active track lifted or no finger remains. */
    if (!game->touch_active || (track_id != game->active_track && game->contact_mask != 0)) {
        return;
    }
    if (track_id == game->active_track) {
        game->last_x = cx;
        game->last_y = cy;
        int32_t dx = cx - game->start_x;
        int32_t dy = cy - game->start_y;
        int32_t dist_sq = dx * dx + dy * dy;
        if (dist_sq > game->max_dist_sq) {
            game->max_dist_sq = dist_sq;
        }
    }
    game->touch_active = false;
    if (game->swipe_triggered) {
        return;
    }

    int32_t dx = game->last_x - game->start_x;
    int32_t dy = game->last_y - game->start_y;
    app_gesture_t swipe = classify_swipe(dx, dy, false);
    if (swipe != GESTURE_NONE) {
        game->tap_pending = false;
        apply_gesture(game, swipe);
        return;
    }

    uint32_t hold_ticks = (uint32_t)(game->state.tick - game->press_tick);
    if (game->max_dist_sq <= TAP_MAX_MOVE_PX * TAP_MAX_MOVE_PX &&
            hold_ticks <= TAP_MAX_HOLD_TICKS) {
        if (game->tap_pending &&
                (uint32_t)(game->state.tick - game->last_tap_tick) <= DOUBLE_TAP_MAX_GAP_TICKS) {
            game->tap_pending = false;
            apply_gesture(game, GESTURE_DOUBLE_TAP);
        } else {
            game->tap_pending = true;
            game->last_tap_tick = game->state.tick;
        }
    } else {
        game->tap_pending = false;
    }
}

void app_game_set_pointer(app_game_handle_t game, int32_t x, int32_t y, bool pressed)
{
    app_game_pointer_event(game, 0, x, y, pressed);
}

void app_game_set_control(app_game_handle_t game, const app_game_control_t *control)
{
    if (!game || !control) {
        return;
    }
    app_game_control_t value = *control;
    if (!(value.steer >= -1.0f)) { /* also rejects NaN */
        value.steer = value.steer < -1.0f ? -1.0f : 0.0f;
    }
    value.steer = value.steer > 1.0f ? 1.0f : value.steer;
    game->state.control = value;
}

void app_game_update(app_game_handle_t game)
{
    if (!game || game->state.paused) {
        return;
    }
    app_game_snapshot_t *state = &game->state;
    ++state->tick;

    if (game->tap_pending &&
            (uint32_t)(state->tick - game->last_tap_tick) > DOUBLE_TAP_MAX_GAP_TICKS) {
        game->tap_pending = false;
    }

    if (state->state == APP_GAME_STATE_LEFT || state->state == APP_GAME_STATE_RIGHT) {
        if (state->turn_remaining > 0) {
            --state->turn_remaining;
        }
        if (state->turn_remaining == 0) {
            state->state = APP_GAME_STATE_STRAIGHT;
            start_turn_transition(game, 0.0f);
        }
    }

    if (game->turn_t < 1.0f) {
        game->turn_t += game->turn_step;
        if (game->turn_t >= 1.0f) {
            game->turn_t = 1.0f;
            state->turn = game->turn_to;
        } else {
            state->turn = game->turn_from + (game->turn_to - game->turn_from) * smoothstep(game->turn_t);
        }
    }

    if (state->state == APP_GAME_STATE_STOP) {
        game->speed_ramp -= 1.0f / (float)SPEED_BRAKE_TICKS;
        if (game->speed_ramp < 0.0f) {
            game->speed_ramp = 0.0f;
        }
    } else {
        game->speed_ramp += 1.0f / (float)SPEED_ACCEL_TICKS;
        if (game->speed_ramp > 1.0f) {
            game->speed_ramp = 1.0f;
        }
    }
    state->speed = smoothstep(game->speed_ramp);

    if (state->state == APP_GAME_STATE_STOP && state->speed <= 0.001f) {
        ++state->idle_tick;
    } else {
        state->idle_tick = 0;
    }

    if (state->intro_hint_active) {
        ++state->intro_hint_tick;
        if (state->intro_hint_tick >= APP_GAME_INTRO_HINT_TICKS) {
            state->intro_hint_active = false;
        }
    }

    if (state->up_hint_active) {
        ++state->up_hint_tick;
        if (state->up_hint_tick >= APP_GAME_INTRO_HINT_TICKS) {
            state->up_hint_active = false;
        }
    }

    if (state->feedback_remaining > 0) {
        --state->feedback_remaining;
        if (state->feedback_remaining == 0) {
            state->feedback_dir = APP_GAME_DIR_NONE;
        }
    }

    state->distance += state->speed * (5.2f / 30.0f);
    if (state->distance >= 1680.0f) {
        state->distance -= 1680.0f;
    }
    state->gait += state->speed;
    if (state->gait >= 480.0f) {
        state->gait -= 480.0f;
    }
}

app_game_snapshot_t app_game_read(app_game_handle_t game)
{
    return game ? game->state : (app_game_snapshot_t) {
        0
    };
}
