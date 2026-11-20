// SPDX-License-Identifier: Apache-2.0
#include <math.h>
#include <stdio.h>
#include <stdlib.h>
#include <string.h>
#include "private/sled_view.h"
#include "raylib_lite_raylib.h"
#if defined(RAYLIB_LITE_GAME_NATIVE)
#include "esp_timer.h"
#define NOW_US() ((uint32_t)esp_timer_get_time())
#else
#define NOW_US() 0U /* profiling is device-only; Host reports its own render time */
#endif

enum { VIEW_SIZE = 480, HORIZON = 213, GAIT_FRAMES = 8, GAIT_TICKS = 2 };

/* Packed RGB565 blend: spread G into the high half so one multiply blends all
 * three channels. Alpha 0..255 is reduced to 0..32 (no division per pixel). */
static inline uint16_t blend(uint16_t dst, uint16_t src, unsigned a)
{
    uint32_t k = (a + 4) >> 3;
    uint32_t d = (dst | ((uint32_t)dst << 16)) & 0x07e0f81fU;
    uint32_t s = (src | ((uint32_t)src << 16)) & 0x07e0f81fU;
    d = ((((s - d) * k) >> 5) + d) & 0x07e0f81fU;
    return (uint16_t)(d | (d >> 16));
}

static int clamp(int n, int lo, int hi)
{
    return n < lo ? lo : (n > hi ? hi : n);
}

/* Alpha below this is skipped and at/above SOLID it is written opaque; the
 * frosted branches are mostly translucent, so this bounds the blend count. */
enum { ALPHA_SKIP = 40, ALPHA_SOLID = 192 };

/* All source art uses immutable RGB565 + alpha; no per-frame allocation.
 * `haze` (0..255) pulls colours toward the horizon fog for aerial perspective.
 * Per-row spans from the packer skip each source row's transparent margins. */
static void sprite(sled_view_t *view, uint16_t *pixels, size_t stride,
                   const sled_image_t *im, int x, int y, int w, int h,
                   bool flip, unsigned opacity, unsigned haze)
{
    if (w <= 0 || h <= 0 || !opacity) {
        return;
    }
    int x0 = clamp(x, 0, VIEW_SIZE), x1 = clamp(x + w, 0, VIEW_SIZE);
    int y0 = clamp(y, 0, VIEW_SIZE), y1 = clamp(y + h, 0, VIEW_SIZE);
    if (x0 >= x1 || y0 >= y1) {
        return;
    }
    int iw = im->width;
    for (int dx = x0; dx < x1; ++dx) {
        int sx = (dx - x) * iw / w;
        view->sample_x[dx] = flip ? iw - 1 - sx : sx;
    }
    for (int dy = y0; dy < y1; ++dy) {
        int sy = (dy - y) * im->height / h;
        int lo = x0, hi = x1;
        if (im->span) {
            int first = im->span[2 * sy], last = im->span[2 * sy + 1];
            if (first > last) {
                continue;
            }
            int a = flip ? iw - 1 - last : first, b = flip ? iw - 1 - first : last;
            lo = clamp(x + a * w / iw, x0, x1);
            hi = clamp(x + ((b + 1) * w + iw - 1) / iw, x0, x1);
        }
        const uint16_t *rgb = im->rgb + (size_t)sy * iw;
        const uint8_t *alpha = im->alpha ? im->alpha + (size_t)sy * iw : NULL;
        uint16_t *row = pixels + (size_t)dy * stride;
        for (int dx = lo; dx < hi; ++dx) {
            int sx = view->sample_x[dx];
            unsigned a = !alpha ? opacity : (opacity == 255 ? alpha[sx] : (alpha[sx] * opacity) >> 8);
            if (a < ALPHA_SKIP) {
                continue;
            }
            uint16_t src = haze ? blend(rgb[sx], view->fog, haze) : rgb[sx];
            row[dx] = a >= ALPHA_SOLID ? src : blend(row[dx], src, a);
        }
    }
}

int sled_view_init(sled_view_t *view)
{
    static const char *const MIPS[2][3] = {
        {"birch", "birch_h", "birch_s"}, {"trees", "trees_h", "trees_s"}
    };
    view->random_state = 0x51ed1234U;
    view->forest = sled_asset("forest");
    view->snow = sled_asset("snow");
    view->lamp = sled_asset("lamp");
    view->sled = sled_asset("sled");
    view->far_forest = sled_asset("far_forest");
    view->rope_red = sled_asset("rope_red");
    view->rope_blue = sled_asset("rope_blue");
    view->rope_joint = sled_asset("rope_joint");
    view->rope_ring = sled_asset("rope_ring");
    bool ok = view->forest && view->snow && view->lamp && view->sled && view->far_forest &&
              view->rope_red && view->rope_blue && view->rope_joint && view->rope_ring;
    for (int level = 0; ok && level < 3; ++level) {
        view->birch_mip[level] = sled_asset(MIPS[0][level]);
        view->trees_mip[level] = sled_asset(MIPS[1][level]);
        ok = view->birch_mip[level] && view->trees_mip[level];
    }
    for (int i = 0; ok && i < GAIT_FRAMES; ++i) {
        char name[16];
        snprintf(name, sizeof(name), "run_%d", i);
        view->dogs[i] = sled_asset(name);
        ok = view->dogs[i] != NULL;
    }
    for (int i = 0; ok && i < SLED_IDLE_FRAMES; ++i) {
        char name[16];
        snprintf(name, sizeof(name), "idle_%d", i);
        view->idle[i] = sled_asset(name);
        ok = view->idle[i] != NULL;
    }
    if (!ok) {
        return -1;
    }
    /* Horizon colour of the plate (source row 232 of 480 at the vanishing point). */
    view->fog = view->forest->rgb[232 * VIEW_SIZE + VIEW_SIZE / 2];
    return 0;
}

/* The same curve drives road markings, roadside objects and pair positions. */
static float road_center(float y, float turn)
{
    float ahead = (VIEW_SIZE - y) / (VIEW_SIZE - HORIZON);
    if (ahead < 0) {
        ahead = 0;
    }
    if (ahead > 1) {
        ahead = 1;
    }
    return 240 + turn * 110 * ahead * ahead;
}

/* Roadside forest: several rows of trees at growing lateral offsets. Perspective
 * makes the near rows sweep past quickly and the far rows drift slowly. Every
 * row spacing divides WORLD_LOOP, so the model's distance wrap is seamless. */
#define WORLD_LOOP 1680.0f
#define CAMERA_SCALE 250.0f
#define CAMERA_HEIGHT 2.1f
#define PROP_NEAR 3.0f
#define PROP_FAR 64.0f /* beyond this the baked far_forest band takes over */
#define TREE_HEIGHT 12.0f
#define LAMP_HEIGHT 4.3f
#define LAMP_LATERAL 4.1f
#define LAMP_SPACING 16.8f

enum { PROP_BIRCH, PROP_TREES, PROP_LAMP };

typedef struct {
    float lateral, jitter, spacing;
    unsigned density; /* 0..255 chance that a slot holds a tree */
} tree_row_t;

static const tree_row_t TREE_ROWS[] = {
    {5.8f, 0.6f, 5.6f, 150},
    {9.5f, 1.4f, 4.2f, 180},
    {14.5f, 2.2f, 3.5f, 205},
    {21.0f, 3.0f, 2.8f, 225},
};

static uint32_t hash32(uint32_t x)
{
    x ^= x >> 16;
    x *= 0x7feb352dU;
    x ^= x >> 15;
    x *= 0x846ca68bU;
    x ^= x >> 16;
    return x;
}

static void add_prop(sled_view_t *view, float depth, float lateral, float height,
                     uint8_t kind, bool flip)
{
    if (depth < PROP_NEAR || depth > PROP_FAR || view->prop_count >= SLED_PROP_CAPACITY) {
        return;
    }
    view->props[view->prop_count++] = (sled_prop_t) {
        depth, lateral, height, kind, flip
    };
}

static int far_first(const void *a, const void *b)
{
    float da = ((const sled_prop_t *)a)->depth, db = ((const sled_prop_t *)b)->depth;
    return da < db ? 1 : (da > db ? -1 : 0);
}

static void collect_props(sled_view_t *view, float distance)
{
    view->prop_count = 0;
    for (unsigned r = 0; r < sizeof(TREE_ROWS) / sizeof(TREE_ROWS[0]); ++r) {
        const tree_row_t *row = &TREE_ROWS[r];
        int slots = (int)(WORLD_LOOP / row->spacing + 0.5f);
        int first = (int)floorf((distance + PROP_NEAR) / row->spacing) - 1;
        int last = (int)ceilf((distance + PROP_FAR) / row->spacing) + 1;
        for (int k = first; k <= last; ++k) {
            uint32_t slot = (uint32_t)(((k % slots) + slots) % slots);
            for (int side = -1; side <= 1; side += 2) {
                uint32_t h = hash32(slot * 16U + r * 2U + (side > 0) + 0x9e3779b9U);
                if ((h & 255U) > row->density) {
                    continue;
                }
                float along = (((h >> 8) & 255U) / 255.0f - 0.5f) * row->spacing * 0.6f;
                float lateral = row->lateral + (((h >> 16) & 255U) / 255.0f - 0.5f) * 2 * row->jitter;
                float height = TREE_HEIGHT * (0.82f + ((h >> 24) & 63U) / 63.0f * 0.38f);
                add_prop(view, k * row->spacing + along - distance, side * lateral, height,
                         (h >> 30) & 1U ? PROP_TREES : PROP_BIRCH, (h >> 31) & 1U);
            }
        }
    }
    /* Lamps stand in pairs at a fixed rhythm on both sides of the trail. */
    int first = (int)floorf((distance + PROP_NEAR) / LAMP_SPACING);
    int last = (int)ceilf((distance + PROP_FAR) / LAMP_SPACING);
    for (int k = first; k <= last; ++k) {
        for (int side = -1; side <= 1; side += 2) {
            add_prop(view, k * LAMP_SPACING - distance, side * LAMP_LATERAL, LAMP_HEIGHT,
                     PROP_LAMP, side < 0);
        }
    }
    qsort(view->props, view->prop_count, sizeof(view->props[0]), far_first);
}

/* Soft warm light: radial alpha falloff, blended in place. */
static void glow(uint16_t *pixels, size_t stride, float cx, float cy, float rx, float ry,
                 uint16_t colour, float peak)
{
    if (rx < 1 || ry < 1) {
        return;
    }
    int x0 = clamp((int)(cx - rx), 0, VIEW_SIZE), x1 = clamp((int)(cx + rx + 1), 0, VIEW_SIZE);
    int y0 = clamp((int)(cy - ry), 0, VIEW_SIZE), y1 = clamp((int)(cy + ry + 1), 0, VIEW_SIZE);
    for (int y = y0; y < y1; ++y) {
        float dy = (y + 0.5f - cy) / ry;
        if (dy * dy >= 1) {
            continue;
        }
        float half = rx * sqrtf(1 - dy * dy);
        int lo = clamp((int)(cx - half), x0, x1), hi = clamp((int)(cx + half) + 1, x0, x1);
        uint16_t *row = pixels + (size_t)y * stride;
        for (int x = lo; x < hi; ++x) {
            float dx = (x + 0.5f - cx) / rx;
            float soft = 1 - dx * dx - dy * dy;
            if (soft > 0) {
                row[x] = blend(row[x], colour, (unsigned)(peak * soft * soft));
            }
        }
    }
}

static void roadside(sled_view_t *view, uint16_t *pixels, size_t stride,
                     const app_game_snapshot_t *state)
{
    static const uint16_t LAMP_LIGHT = 0xfe4f; /* warm sodium yellow, RGB(255,200,120) */
    collect_props(view, state->distance);
    for (unsigned i = 0; i < view->prop_count; ++i) {
        const sled_prop_t *p = &view->props[i];
        float scale = CAMERA_SCALE / p->depth;
        int foot = HORIZON + (int)(CAMERA_HEIGHT * scale);
        float x = road_center(foot, state->turn) + p->lateral * scale;
        int h = (int)(p->height * scale);
        /* Fade in at the far edge, out as a trunk passes the camera. */
        float far = (PROP_FAR - p->depth) / 14.0f, near = (p->depth - PROP_NEAR) / 1.5f;
        float fade = far < near ? far : near;
        unsigned opacity = fade >= 1 ? 255 : (unsigned)(fade * 255);
        unsigned haze = (unsigned)clamp((int)((p->depth - 12) * 2.4f), 0, 150);
        if (p->kind == PROP_LAMP) {
            int w = h * view->lamp->width / view->lamp->height;
            float head = foot - h * 0.86f;
            glow(pixels, stride, x - p->lateral * scale * 0.25f, foot - 0.15f * scale,
                 1.9f * scale, 0.45f * scale, LAMP_LIGHT, 70.0f * opacity / 255);
            sprite(view, pixels, stride, view->lamp, (int)x - w / 2, foot - h, w, h, p->flip,
                   opacity, haze / 2);
            glow(pixels, stride, x, head, 0.9f * scale, 0.9f * scale, LAMP_LIGHT,
                 120.0f * opacity / 255);
            continue;
        }
        /* Smallest mip that still has at least ~0.7 source pixels per screen pixel. */
        const sled_image_t *const *mips = p->kind == PROP_BIRCH ? view->birch_mip : view->trees_mip;
        int level = 2;
        while (level > 0 && mips[level]->height * 10 < h * 7) {
            --level;
        }
        const sled_image_t *tree = mips[level];
        /* The half mip has its haze baked in by the packer; only the far,
         * small quarter-size trees pay for per-pixel haze. */
        haze = level == 2 ? haze : 0;
        int w = h * tree->width / tree->height;
        sprite(view, pixels, stride, tree, (int)x - w / 2, foot - h, w, h, p->flip, opacity, haze);
    }
}

static void landscape(sled_view_t *view, uint16_t *pixels, size_t stride,
                      const app_game_snapshot_t *state)
{
    const uint16_t *base = view->forest->rgb;
    for (int y = 0; y < VIEW_SIZE; ++y) {
        uint16_t *row = pixels + (size_t)y * stride;
        if (y <= HORIZON) {
            /* Register the source horizon (48%) to the game's camera horizon. */
            int sy = y * 230 / HORIZON;
            memcpy(row, base + (size_t)sy * VIEW_SIZE, VIEW_SIZE * sizeof(uint16_t));
            continue;
        }
        float depth = 520.0f / (y - HORIZON);
        int v = (int)((depth + state->distance) * 30.0f) & 255;
        int step = (int)(depth * 30.0f * 256 / 250.0f);
        int center = (int)road_center(y, state->turn);
        int u = (128 << 8) - center * step;
        int sy = clamp(230 + (y - HORIZON) * 250 / (VIEW_SIZE - HORIZON), 0, 479);
        unsigned fade = (unsigned)clamp((y - HORIZON) * 255 / 90, 0, 255);
        int left = center - (int)((y - HORIZON) * 0.42f);
        int right = center + (int)((y - HORIZON) * 0.42f);
        int rut = 1 + (y - HORIZON) / 90;
        const uint16_t *plate = base + (size_t)sy * VIEW_SIZE;
        for (int x = 0; x < VIEW_SIZE; ++x, u += step) {
            uint16_t snow = view->snow->rgb[v * 256 + ((u >> 8) & 255)];
            row[x] = fade == 255 ? snow : blend(plate[clamp(x - center + 240, 0, 479)], snow, fade);
        }
        if (y > HORIZON + 8) {
            /* Twin trail edges: a soft core with a brighter rim, only near each edge. */
            for (int e = 0; e < 2; ++e) {
                int edge_x = e ? right : left;
                for (int x = clamp(edge_x - rut, 0, VIEW_SIZE); x <= edge_x + rut && x < VIEW_SIZE; ++x) {
                    bool rim = abs(x - edge_x) == rut;
                    row[x] = blend(row[x], rim ? 0xd71f : 0x73f7, rim ? 75 : 28);
                }
            }
        }
    }
    /* Distant forest wall: column 480 of the band sits on the vanishing point. */
    const sled_image_t *band = view->far_forest;
    int band_x = (int)road_center(HORIZON + 1, state->turn) - band->width / 2;
    sprite(view, pixels, stride, band, band_x, HORIZON + 4 - band->height,
           band->width, band->height, false, 255, 0);
}

static float random_unit(sled_view_t *view)
{
    uint32_t x = view->random_state;
    x ^= x << 13;
    x ^= x >> 17;
    x ^= x << 5;
    view->random_state = x;
    return (x & 65535U) / 65535.0f;
}

void sled_view_update(sled_view_t *view, const app_game_snapshot_t *state)
{
    if (state->paused) {
        return;
    }
    for (unsigned i = 0; i < SLED_POWDER_CAPACITY; ++i) {
        sled_powder_t *p = &view->powder[i];
        if (p->age >= p->life) {
            continue;
        }
        p->age += 1;
        p->x += p->vx;
        p->y += p->vy;
        p->vx *= 0.975f;
        p->vy += p->kind ? 0.075f : 0.025f;
    }
    if (state->speed > 0.05f) {
        view->emission += state->speed * 0.25f;
    } else {
        view->emission = 0;
    }
    if (view->emission >= 1) {
        view->emission -= 1;
        for (int pair = 0; pair < 3; ++pair) {
            float bottom = 281 + pair * 63;
            float gap = 20 + pair * 22;
            for (int side = -1; side <= 1; side += 2) {
                float center = road_center(bottom, state->turn) + side * gap;
                for (int n = 0; n < 4; ++n) {
                    sled_powder_t *p = &view->powder[view->next_particle];
                    view->next_particle = (view->next_particle + 1) % SLED_POWDER_CAPACITY;
                    p->x = center + (random_unit(view) - 0.5f) * (10 + pair * 7);
                    p->y = bottom - 7 + random_unit(view) * 4;
                    p->vx = (random_unit(view) - 0.5f) * (0.7f + pair * 0.6f);
                    p->vy = -0.6f - random_unit(view) * 0.8f;
                    p->age = 0;
                    p->kind = n % 2;
                    p->pair = (uint8_t)pair;
                    p->life = p->kind ? 15 + random_unit(view) * 10 : 22 + random_unit(view) * 12;
                    if (!p->kind) {
                        p->vy = 0.3f + random_unit(view) * 0.5f;
                    }
                    p->radius = p->kind ? 0.8f + pair * 0.3f : 3.5f + pair * 2.3f;
                }
            }
        }
    }
    view->particle_count = 0;
    for (unsigned i = 0; i < SLED_POWDER_CAPACITY; ++i) {
        if (view->powder[i].age < view->powder[i].life) {
            ++view->particle_count;
        }
    }
}

/* Below this alpha a dust texel is invisible after the 5-bit blend; skip it. */
enum { POWDER_ALPHA_MIN = 12 };

static void draw_powder(const sled_view_t *view, uint16_t *pixels, size_t stride, int pair)
{
    for (unsigned i = 0; i < SLED_POWDER_CAPACITY; ++i) {
        const sled_powder_t *p = &view->powder[i];
        if (p->age >= p->life || p->pair != pair) {
            continue;
        }
        float t = p->age / p->life;
        float radius = p->kind ? p->radius : p->radius * (1 + t * 2.4f);
        float rx = p->kind ? radius : radius * 1.5f;
        float ry = p->kind ? radius : radius * 0.75f;
        float peak = (p->kind ? 210 : 165) * (1 - t) * (1 - t);
        if (peak < POWDER_ALPHA_MIN) {
            continue; /* fully faded: nothing visible to blend */
        }
        float inv_rx = 1.0f / rx, inv_ry = 1.0f / ry;
        int x0 = clamp((int)(p->x - rx), 0, VIEW_SIZE - 1);
        int x1 = clamp((int)(p->x + rx + 1), 0, VIEW_SIZE);
        int y0 = clamp((int)(p->y - ry), 0, VIEW_SIZE - 1);
        int y1 = clamp((int)(p->y + ry + 1), 0, VIEW_SIZE);
        for (int y = y0; y < y1; ++y) {
            float dy = (y + 0.5f - p->y) * inv_ry, dy2 = dy * dy;
            if (dy2 >= 1) {
                continue;
            }
            float half = rx * sqrtf(1 - dy2);
            int lo = clamp((int)(p->x - half), x0, x1), hi = clamp((int)(p->x + half) + 1, x0, x1);
            for (int x = lo; x < hi; ++x) {
                float dx = (x + 0.5f - p->x) * inv_rx;
                float soft = 1 - dx * dx - dy2;
                unsigned alpha = soft > 0 ? (unsigned)(peak * soft * soft) : 0;
                if (alpha >= POWDER_ALPHA_MIN) {
                    size_t index = (size_t)y * stride + x;
                    pixels[index] = blend(pixels[index], 0xef7f, alpha);
                }
            }
        }
    }
}

/* Textured rope from (x0, y0) to (x1, y1). The texture is a real rope photo
 * strip (length along y); it is sampled at constant aspect so the braid keeps
 * its pitch, tiles along the length and keeps its soft alpha edges. */
static void rope(uint16_t *pixels, size_t stride, const sled_image_t *tex,
                 float x0, float y0, float x1, float y1, float width)
{
    float dx = x1 - x0, dy = y1 - y0;
    float length = sqrtf(dx * dx + dy * dy);
    if (length < 0.5f || width < 0.5f) {
        return;
    }
    float ux = dx / length, uy = dy / length, half = width * 0.5f;
    float texel = tex->width / width;
    int bx0 = clamp((int)fminf(x0, x1) - (int)half - 1, 0, VIEW_SIZE);
    int bx1 = clamp((int)fmaxf(x0, x1) + (int)half + 2, 0, VIEW_SIZE);
    int by0 = clamp((int)fminf(y0, y1) - (int)half - 1, 0, VIEW_SIZE);
    int by1 = clamp((int)fmaxf(y0, y1) + (int)half + 2, 0, VIEW_SIZE);
    for (int y = by0; y < by1; ++y) {
        uint16_t *row = pixels + (size_t)y * stride;
        for (int x = bx0; x < bx1; ++x) {
            float rx = x + 0.5f - x0, ry = y + 0.5f - y0;
            float t = rx * ux + ry * uy, s = ry * ux - rx * uy;
            if (t < 0 || t > length || fabsf(s) >= half) {
                continue;
            }
            int u = clamp((int)((s + half) * texel), 0, tex->width - 1);
            int v = (int)(t * texel) % tex->height;
            size_t index = (size_t)v * tex->width + u;
            unsigned a = tex->alpha[index];
            if (a > 8) {
                row[x] = a >= 250 ? tex->rgb[index] : blend(row[x], tex->rgb[index], a);
            }
        }
    }
}

static void dog_team(sled_view_t *view, uint16_t *pixels, size_t stride,
                     const app_game_snapshot_t *state)
{
    enum { RING_Y = 398, TOWLINE_Y = 455 };
    float time = state->gait / 30.0f;
    float ring_x = road_center(RING_Y, state->turn);
    for (int pair = 0; pair < 3; ++pair) {
        int h = 67 + pair * 41;
        int w = h * 96 / 164;
        int bottom = 281 + pair * 63;
        int gap = 20 + pair * 22;
        int road = (int)road_center(bottom, state->turn);
        /* Gangline junctions ride at harness height; the wheel pair's tuglines
         * meet at the metal ring, as in the reference render. */
        float joint_x = road, joint_y = bottom - h * 0.42f;
        if (pair == 2) {
            joint_x = ring_x;
            joint_y = RING_Y;
        }
        float line_w = 3.0f + pair * 1.2f;
        if (pair < 2) {
            int next_bottom = bottom + 63, next_h = h + 41;
            float next_x = pair == 1 ? ring_x : road_center(next_bottom, state->turn);
            float next_y = pair == 1 ? RING_Y : next_bottom - next_h * 0.42f;
            rope(pixels, stride, view->rope_red, joint_x, joint_y, next_x, next_y, line_w);
        }
        for (int side = 0; side < 2; ++side) {
            int dog = pair * 2 + side;
            int frame = ((int)(state->gait / GAIT_TICKS) + dog * 3) % GAIT_FRAMES;
            const sled_image_t *dog_image = view->dogs[frame];
            if (state->state == APP_GAME_STATE_STOP && state->speed <= 0.001f) {
                /* Tail wag exists only at rest: 7 real frames ping-pong at
                 * 15 fps, phase-shifted per dog so the team stays lively
                 * without moving in unison. */
                static const int wag_sequence[12] = {0, 1, 2, 3, 4, 5, 6, 5, 4, 3, 2, 1};
                dog_image = view->idle[wag_sequence[((state->idle_tick / 2) + dog * 2) % 12]];
            }
            int bob = (int)(sinf(time * 11.8f + dog * 1.3f) * (1.1f + pair * 0.4f) * state->speed);
            int center = road + (side ? gap : -gap);
            int y = bottom - h + bob;
            DrawEllipse(center, bottom - 4, w / 3, 4 + pair, (Color) {
                68, 86, 120, 45
            });
            float harness_x = center + (side ? -w : w) * 0.18f;
            rope(pixels, stride, view->rope_red, joint_x, joint_y, harness_x, y + h * 0.36f,
                 line_w * 0.8f);
            int sprite_w = h * dog_image->width / dog_image->height;
            sprite(view, pixels, stride, dog_image, center - sprite_w / 2, y, sprite_w, h, side == 1, 255, 0);
        }
        if (pair < 2) {
            int joint = (int)(line_w * 3.0f);
            sprite(view, pixels, stride, view->rope_joint, (int)joint_x - joint / 2,
                   (int)joint_y - joint / 2, joint, joint, false, 255, 0);
        }
        draw_powder(view, pixels, stride, pair);
    }
    rope(pixels, stride, view->rope_blue, ring_x, RING_Y + 6, VIEW_SIZE / 2, TOWLINE_Y, 11);
    sprite(view, pixels, stride, view->rope_ring, (int)ring_x - 13, RING_Y - 14, 26, 26, false, 255, 0);
}

/* Unsigned distance from point (px, py) to line segment (ax, ay)-(bx, by). */
static float sd_segment(float px, float py, float ax, float ay, float bx, float by)
{
    float pax = px - ax, pay = py - ay;
    float bax = bx - ax, bay = by - ay;
    float denom = bax * bax + bay * bay;
    float h = denom > 0.0f ? (pax * bax + pay * bay) / denom : 0.0f;
    if (h < 0.0f) {
        h = 0.0f;
    } else if (h > 1.0f) {
        h = 1.0f;
    }
    float dx = pax - bax * h;
    float dy = pay - bay * h;
    return sqrtf(dx * dx + dy * dy);
}

/* Pure white translucent double-chevron icon on the 480x480 circular safe ring.
 * A subtle cool-navy outer halo keeps the white strokes legible over bright snow. */
static void draw_direction_icon(uint16_t *pixels, size_t stride,
                                app_game_dir_t dir, unsigned opacity, float shift)
{
    if (dir == APP_GAME_DIR_NONE || opacity < 8) {
        return;
    }
    static const uint16_t ICON_WHITE = 0xffff;
    static const uint16_t ICON_HALO = 0x10a4;
    const float half_w = 2.6f;
    const float aa = 1.2f;
    const float halo_w = 4.5f;
    const int radius = 24;

    float cx = 240.0f, cy = 240.0f;
    float fx = 0.0f, fy = 0.0f;
    switch (dir) {
    case APP_GAME_DIR_UP:
        cx = 240.0f;
        cy = 64.0f - shift;
        fy = -1.0f;
        break;
    case APP_GAME_DIR_DOWN:
        cx = 240.0f;
        cy = 416.0f + shift;
        fy = 1.0f;
        break;
    case APP_GAME_DIR_LEFT:
        cx = 64.0f - shift;
        cy = 240.0f;
        fx = -1.0f;
        break;
    case APP_GAME_DIR_RIGHT:
        cx = 416.0f + shift;
        cy = 240.0f;
        fx = 1.0f;
        break;
    default:
        return;
    }

    int x0 = clamp((int)(cx - radius), 0, VIEW_SIZE);
    int x1 = clamp((int)(cx + radius + 1), 0, VIEW_SIZE);
    int y0 = clamp((int)(cy - radius), 0, VIEW_SIZE);
    int y1 = clamp((int)(cy + radius + 1), 0, VIEW_SIZE);

    for (int y = y0; y < y1; ++y) {
        uint16_t *row = pixels + (size_t)y * stride;
        float dy = y + 0.5f - cy;
        for (int x = x0; x < x1; ++x) {
            float dx = x + 0.5f - cx;
            float u = dx * fx + dy * fy;
            float v = fabsf(-dx * fy + dy * fx);

            /* Lead chevron (brighter) and trailing chevron (softer swipe cue). */
            float d_lead = sd_segment(u, v, 12.0f, 0.0f, -1.0f, 13.0f);
            float d_tail = sd_segment(u, v, -1.0f, 0.0f, -12.0f, 11.0f);
            float d_min = d_lead < d_tail ? d_lead : d_tail;
            if (d_min > half_w + halo_w) {
                continue;
            }

            float cov_lead = 0.5f + (half_w - d_lead) / aa;
            if (cov_lead < 0.0f) {
                cov_lead = 0.0f;
            } else if (cov_lead > 1.0f) {
                cov_lead = 1.0f;
            }
            float cov_tail = 0.5f + (half_w - d_tail) / aa;
            if (cov_tail < 0.0f) {
                cov_tail = 0.0f;
            } else if (cov_tail > 1.0f) {
                cov_tail = 1.0f;
            }
            float cov = cov_lead > cov_tail * 0.65f ? cov_lead : cov_tail * 0.65f;

            float halo_t = 1.0f - (d_min - half_w) / halo_w;
            if (halo_t > 0.0f) {
                if (halo_t > 1.0f) {
                    halo_t = 1.0f;
                }
                unsigned halo_a = (unsigned)(opacity * 0.28f * halo_t * halo_t);
                if (halo_a >= 8) {
                    row[x] = blend(row[x], ICON_HALO, halo_a);
                }
            }
            unsigned white_a = (unsigned)(opacity * cov);
            if (white_a >= 8) {
                row[x] = blend(row[x], ICON_WHITE, white_a);
            }
        }
    }
}

static void hint_pulse_params(uint32_t hint_tick, unsigned *out_alpha, float *out_shift)
{
    uint32_t local = hint_tick % APP_GAME_INTRO_PULSE_TICKS;
    float phase = (float)local / (float)APP_GAME_INTRO_PULSE_TICKS;
    float pulse = sinf(3.14159265f * phase);
    *out_alpha = (unsigned)(pulse * 195.0f);
    *out_shift = (pulse - 0.3f) * 5.0f;
}

static void draw_touch_hints(uint16_t *pixels, size_t stride, const app_game_snapshot_t *state)
{
    if (state->intro_hint_active) {
        unsigned alpha = 0;
        float shift = 0.0f;
        hint_pulse_params(state->intro_hint_tick, &alpha, &shift);
        draw_direction_icon(pixels, stride, APP_GAME_DIR_LEFT, alpha, shift);
        draw_direction_icon(pixels, stride, APP_GAME_DIR_RIGHT, alpha, shift);
        draw_direction_icon(pixels, stride, APP_GAME_DIR_DOWN, alpha, shift);
    }

    if (state->up_hint_active) {
        unsigned alpha = 0;
        float shift = 0.0f;
        hint_pulse_params(state->up_hint_tick, &alpha, &shift);
        draw_direction_icon(pixels, stride, APP_GAME_DIR_UP, alpha, shift);
    }

    if (state->feedback_dir != APP_GAME_DIR_NONE && state->feedback_remaining > 0) {
        uint32_t elapsed = APP_GAME_FEEDBACK_TICKS - state->feedback_remaining;
        float env;
        if (elapsed <= 1) {
            env = 0.75f;
        } else if (elapsed == 2) {
            env = 1.0f;
        } else {
            float rem = 1.0f - (float)(elapsed - 2) / (float)(APP_GAME_FEEDBACK_TICKS - 2);
            env = rem > 0.0f ? rem * rem : 0.0f;
        }
        float t = (float)elapsed / (float)APP_GAME_FEEDBACK_TICKS;
        float shift = -4.0f + 10.0f * (1.0f - (1.0f - t) * (1.0f - t));
        unsigned alpha = (unsigned)(env * 235.0f);
        draw_direction_icon(pixels, stride, state->feedback_dir, alpha, shift);
    }
}

int sled_view_render(sled_view_t *view, const app_game_snapshot_t *state)
{
    int width, height;
    size_t stride;
    uint16_t *pixels = raylib_lite_raylib_get_framebuffer(&width, &height, &stride);
    if (!pixels || width != VIEW_SIZE || height != VIEW_SIZE || stride < VIEW_SIZE) {
        return -1;
    }
    uint32_t t0 = NOW_US();
    landscape(view, pixels, stride, state);
    uint32_t t1 = NOW_US();
    roadside(view, pixels, stride, state);
    uint32_t t2 = NOW_US();
    dog_team(view, pixels, stride, state);
    uint32_t t3 = NOW_US();
    int bob = (int)(sinf(state->gait / 30.0f * 11.8f) * 1.5f * state->speed);
    sprite(view, pixels, stride, view->sled, -5, 443 + bob, 490, 155, false, 255, 0);
    uint32_t t4 = NOW_US();
    draw_touch_hints(pixels, stride, state);
    uint32_t t5 = NOW_US();
    view->layer_us[SLED_LAYER_GROUND] = t1 - t0;
    view->layer_us[SLED_LAYER_PROPS] = t2 - t1;
    view->layer_us[SLED_LAYER_TEAM] = t3 - t2;
    view->layer_us[SLED_LAYER_SLED] = t4 - t3;
    view->layer_us[SLED_LAYER_HUD] = t5 - t4;
    return 0;
}
