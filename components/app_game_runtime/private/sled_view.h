// SPDX-License-Identifier: Apache-2.0
#pragma once
#include <stdint.h>
#include "sled_assets.h"
#include "../../app_game/include/app_game.h"

enum { SLED_POWDER_CAPACITY = 256, SLED_PROP_CAPACITY = 320 };
enum { SLED_LAYER_GROUND, SLED_LAYER_PROPS, SLED_LAYER_TEAM, SLED_LAYER_SLED, SLED_LAYER_COUNT };
typedef struct {
    float x, y, vx, vy, age, life, radius;
    uint8_t kind, pair;
} sled_powder_t;
/* One roadside billboard (tree or lamp) collected for depth sorting. */
typedef struct {
    float depth, lateral, height;
    uint8_t kind;
    bool flip;
} sled_prop_t;
/* Per-renderer scratch and fixed particle pool. Owning loop only. */
typedef struct {
    const sled_image_t *forest, *snow, *dogs[8], *lamp, *sled;
    const sled_image_t *birch_mip[3], *trees_mip[3], *far_forest; /* full, 1/2, 1/4 */
    const sled_image_t *rope_red, *rope_blue, *rope_joint, *rope_ring;
    uint16_t fog;
    int sample_x[480];
    sled_prop_t props[SLED_PROP_CAPACITY];
    sled_powder_t powder[SLED_POWDER_CAPACITY];
    uint32_t random_state;
    unsigned next_particle, particle_count, prop_count;
    float emission;
    uint32_t layer_us[SLED_LAYER_COUNT]; /* device profiling: last frame per layer */
} sled_view_t;
/** Resolve the embedded art by name; returns 0, or -1 if any image is missing. */
int sled_view_init(sled_view_t *view);
void sled_view_update(sled_view_t *view, const app_game_snapshot_t *state);
int sled_view_render(sled_view_t *view, const app_game_snapshot_t *state);
