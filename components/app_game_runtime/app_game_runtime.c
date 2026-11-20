// SPDX-License-Identifier: Apache-2.0
#include <stdio.h>
#include "include/app_game_runtime.h"
/* Engine Host accepts source lists, not component include paths. Reference only
 * the model's public header so these translation units work on both targets. */
#include "../app_game/include/app_game.h"
#include "private/game_config.h"
#include "private/sled_view.h"
#include "raylib_lite_raylib.h"
#if defined(RAYLIB_LITE_GAME_NATIVE)
#include "esp_log.h"
#include "esp_timer.h"
#endif

typedef struct {
    app_game_handle_t game;
    sled_view_t view;
#if defined(RAYLIB_LITE_GAME_NATIVE)
    int64_t stats_start_us, render_us; /* frame-time log on device only */
    unsigned stats_frames;
#endif
} host_state_t;

#if defined(RAYLIB_LITE_GAME_NATIVE)
enum { STATS_FRAMES = 150 };
static void log_frame_stats(host_state_t *state, int64_t begin_us, int64_t end_us)
{
    if (!state->stats_frames) {
        state->stats_start_us = begin_us;
        state->render_us = 0;
    }
    state->render_us += end_us - begin_us;
    if (++state->stats_frames == STATS_FRAMES) {
        int64_t span = end_us - state->stats_start_us;
        const uint32_t *layer = state->view.layer_us;
        ESP_LOGI("husky", "fps %.1f, draw %lld us/frame (last: ground %lu, props %lu/%u, team %lu, sled %lu)",
                 span > 0 ? STATS_FRAMES * 1e6 / (double)span : 0.0,
                 (long long)(state->render_us / STATS_FRAMES),
                 (unsigned long)layer[SLED_LAYER_GROUND], (unsigned long)layer[SLED_LAYER_PROPS],
                 state->view.prop_count, (unsigned long)layer[SLED_LAYER_TEAM],
                 (unsigned long)layer[SLED_LAYER_SLED]);
        state->stats_frames = 0;
    }
}
#endif

static int initialize(void *value, const char *asset_root)
{
    (void)asset_root;
    host_state_t *state = value;
    const app_game_config_t config = {GAME_WIDTH, GAME_HEIGHT};
    if (app_game_create(&config, &state->game) != APP_GAME_OK) {
        return -1;
    }
    if (sled_view_init(&state->view) != 0) {
        app_game_destroy(&state->game);
        return -1;
    }
    InitWindow(GAME_WIDTH, GAME_HEIGHT, GAME_NAME);
    SetTargetFPS(GAME_TICK_HZ);
    return 0;
}

static void shutdown(void *value)
{
    host_state_t *state = value;
    app_game_destroy(&state->game);
}

static void input(void *value, const raylib_lite_game_input_v1_t *event)
{
    /* Autonomous visual prototype: device touch/actions cannot steer or pause. */
    (void)value;
    (void)event;
}

static void update(void *value)
{
    host_state_t *state = value;
    app_game_update(state->game);
    app_game_snapshot_t snapshot = app_game_read(state->game);
    sled_view_update(&state->view, &snapshot);
}

static int render(void *value)
{
    if (!((host_state_t *)value)->game) {
        return -1;
    }
    BeginDrawing();
    if (!raylib_lite_raylib_frame_available()) {
        EndDrawing();
        return -1;
    }
    host_state_t *state = value;
    app_game_snapshot_t snapshot = app_game_read(state->game);
#if defined(RAYLIB_LITE_GAME_NATIVE)
    int64_t begin_us = esp_timer_get_time();
#endif
    int result = sled_view_render(&state->view, &snapshot);
    EndDrawing();
#if defined(RAYLIB_LITE_GAME_NATIVE)
    log_frame_stats(state, begin_us, esp_timer_get_time());
#endif
    return result;
}

static uint32_t state_hash(const void *value)
{
    const app_game_snapshot_t state = app_game_read(((const host_state_t *)value)->game);
    /* Hash named fields, avoiding platform-dependent struct padding. */
    uint32_t hash = state.tick;
    hash = hash * 31U + (uint32_t)state.pointer_x;
    hash = hash * 31U + (uint32_t)state.pointer_y;
    hash = hash * 31U + state.pointer_down;
    return hash * 31U + state.paused;
}

static int state_json(const void *value, char *output, size_t capacity)
{
    if (!output || !capacity) {
        return -1;
    }
    const app_game_snapshot_t state = app_game_read(((const host_state_t *)value)->game);
    static const char *const stages[] = {"straight", "left", "right", "straight_return", "stop"};
    const host_state_t *host = value;
    int size = snprintf(output, capacity,
                        "{\"mode\":\"autonomous\",\"dog_count\":6,\"phase\":\"%s\",\"stage\":\"%s\","
                        "\"tick\":%lu,\"cycle_tick\":%lu,\"speed\":%.4f,\"turn\":%.4f,"
                        "\"distance\":%.4f,\"gait\":%.4f,\"powder_count\":%u,"
                        "\"pointer_down\":false,\"state_hash\":\"%08lx\"}",
                        state.paused ? "paused" : "running", stages[state.stage],
                        (unsigned long)state.tick, (unsigned long)state.cycle_tick,
                        (double)state.speed, (double)state.turn, (double)state.distance,
                        (double)state.gait, host->view.particle_count, (unsigned long)state_hash(value));
    return size < 0 || (size_t)size >= capacity ? -1 : size;
}

static const raylib_lite_game_module_v1_t s_module = {
    .descriptor = {
        RAYLIB_LITE_GAME_MODULE_ABI_V1, GAME_NAME, GAME_NAME,
        GAME_WIDTH, GAME_HEIGHT, GAME_TICK_HZ, 1
    },
    .state_size = sizeof(host_state_t),
    .initialize = initialize, .shutdown = shutdown, .input = input,
    .update = update, .render = render,
    .state_hash = state_hash, .state_json = state_json,
};

const raylib_lite_game_module_v1_t *app_game_runtime_module(void)
{
    return &s_module;
}
