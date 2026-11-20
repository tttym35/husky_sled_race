// SPDX-License-Identifier: Apache-2.0
/* The Engine supplies app_main and startup order. This file only selects our
 * application adapter. Use its public header for the Host source-list runner. */
#include "../components/app_game_runtime/include/app_game_runtime.h"

const raylib_lite_game_module_v1_t *raylib_lite_game_module_v1(void)
{
    return app_game_runtime_module();
}

#ifdef RAYLIB_LITE_GAME_NATIVE
/* Raster assets are immutable C data owned by app_game_runtime. */
void raylib_lite_register_native_assets(void) {}
#endif
