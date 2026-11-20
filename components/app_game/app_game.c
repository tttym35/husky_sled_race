// SPDX-License-Identifier: Apache-2.0
#include <stdlib.h>
#include "include/app_game.h"

struct app_game {
    app_game_config_t config;
    app_game_snapshot_t state;
};

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
        game->state = (app_game_snapshot_t) {
            0
        };
    }
}

void app_game_set_paused(app_game_handle_t game, bool paused)
{
    if (game) {
        game->state.paused = paused;
    }
}

void app_game_set_pointer(app_game_handle_t game, int32_t x, int32_t y, bool pressed)
{
    if (!game) {
        return;
    }
    game->state.pointer_x = x < 0 ? 0 : (x >= game->config.width ? game->config.width - 1 : x);
    game->state.pointer_y = y < 0 ? 0 : (y >= game->config.height ? game->config.height - 1 : y);
    game->state.pointer_down = pressed;
    /* Add touch-driven game logic here. */
}

void app_game_set_control(app_game_handle_t game, const app_game_control_t *control)
{
    if (!game || !control) {
        return;
    }
    app_game_control_t value = *control;
    if (!(value.steer >= -1)) { /* also rejects NaN */
        value.steer = value.steer < -1 ? -1 : 0;
    }
    value.steer = value.steer > 1 ? 1 : value.steer;
    game->state.control = value;
}

void app_game_update(app_game_handle_t game)
{
    if (!game || game->state.paused) {
        return;
    }
    ++game->state.tick;
    app_game_snapshot_t *state = &game->state;
    state->cycle_tick = (state->cycle_tick + 1) % APP_DEMO_CYCLE_TICKS;
    state->stage = (app_demo_stage_t)(state->cycle_tick / APP_DEMO_STAGE_TICKS);
    uint32_t local = state->cycle_tick % APP_DEMO_STAGE_TICKS;
    float ease = local < 45 ? local / 45.0f : 1.0f;
    ease = ease * ease * (3.0f - 2.0f * ease);
    switch (state->stage) {
    case APP_DEMO_LEFT: state->turn = -ease; break;
    case APP_DEMO_RIGHT: state->turn = -1.0f + 2.0f * ease; break;
    case APP_DEMO_STRAIGHT_RETURN: state->turn = 1.0f - ease; break;
    default: state->turn = 0; break;
    }
    state->speed = 1;
    if (state->stage == APP_DEMO_STRAIGHT) {
        state->speed = ease;
    } else if (state->stage == APP_DEMO_STOP) {
        state->speed = 0;
    } else if (state->stage == APP_DEMO_STRAIGHT_RETURN && local >= 135) {
        float braking = (local - 135) / 45.0f;
        state->speed = 1.0f - braking * braking * (3.0f - 2.0f * braking);
    }
    state->distance += state->speed * (5.2f / 30.0f);
    if (state->distance >= 1680) {
        state->distance -= 1680;
    }
    state->gait += state->speed;
    if (state->gait >= 480) {
        state->gait -= 480;
    }
}

app_game_snapshot_t app_game_read(app_game_handle_t game)
{
    return game ? game->state : (app_game_snapshot_t) {
        0
    };
}
