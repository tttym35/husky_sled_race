idf_component_register(SRCS "app_game_runtime.c" "sled_view.c" "private/sled_assets.c"
    INCLUDE_DIRS "include"
    PRIV_INCLUDE_DIRS "private"
    REQUIRES examples_common
    PRIV_REQUIRES app_game raylib-lite-engine esp_timer log)
target_compile_definitions(${COMPONENT_LIB} PRIVATE RAYLIB_LITE_GAME_NATIVE=1)
