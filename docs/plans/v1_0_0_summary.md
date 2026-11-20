# husky_sled_race v1.0.0 计划摘要

日期：2026-11-20

本文件是 v1.0.0 的合并说明。两份原始头脑风暴同目录存档，不改原文：

- `codex_plan_brainstorm.md`：Codex 版计划，仓库根目录的 `codex-plan头脑风暴.md` 为同一原文。
- `claude_plan_brainstorm.md`：Claude 版计划，含热情值玩法草案、两套操控方案，以及 2026-11-20 的自动奔跑 v1 重做计划。

## v1.0.0 基线来源

| 内容 | 来源 | 说明 |
|---|---|---|
| 运行代码 | `husky_sled_race_codex_claude` 分支 `feat/husky_sled_race_codex_claude` 的 `260fc12` | 效果最好的一版，经本地路径 fetch 后快进合入 `main`。含 codex 线的 `f67b9ec`、`1b229ba` 两个前置提交 |
| 素材 | codex、claude 两条 dev 线和原 main 工作区的并集 | 见下方素材清单 |
| 计划文档 | codex 与 claude 两份头脑风暴 | 原文存档加本摘要 |

dev 仓库 `husky_sled_race_codex`、`husky_sled_race_claude`、`husky_sled_race_codex_claude` 本地原样保留，继续作备份和后续开发场地。本仓库不依赖它们运行。

## v1.0.0 实际范围

当前版本是自动奔跑的视觉原型，还没有接入操控和计分：

- 六只哈士奇三排两两成对，八帧跑步动画，步相错开。
- 约 30 秒状态循环：直行 6 秒、左转 6 秒、右转 6 秒、直行 6 秒、减速停下 6 秒，转弯和速度平滑过渡，停下时用跑步序列第 8 帧站定。
- 第一人称雪橇视角：雪地透视地面和车辙、白桦与路灯独立精灵后移、牵引绳纹理、雪橇扶手、落爪扬起的雪花和雪尘，停下后粒子消散且不再产生。
- 输入、计分、圈速、音频和 IMU 在本版有意留空。

## 素材清单

已合入的素材按用途分四组：

- `assets/review/2026_11_19/`：评审图、参考帧、`turns_v2` 转弯底图和合成参考图、`ui_v1` 界面评审图，以及本次新增的 `library_v1` 屏幕和素材总览图。
- `assets_src/`：源图和生成管线。含 codex 线的跑步图、场景图、雪林图和 `prepare_art.py`；含 claude 线的素材库切图 `library/`、素材库工具 `library_tools/`、界面评审工具 `ui_review/`、四张 `husky_*_source.png` 源图和 atlas 打包配置。
- `assets/generated/`：claude 线打包好的四个 atlas 加 `assets_ids.h` 和校验文件，作为另一套渲染路线的现成产物保留，当前 `sled_view` 运行时没有引用它们。
- `components/app_game_runtime/private/generated/`：当前运行时实际使用的 RGB565 精灵数据，由 `prepare_art.py` 从 `assets_src/` 源图生成。

同名文件冲突只有一处已裁决：`assets/review/2026_11_19/prompts.json` 保留 claude 线的版本，它比 codex 线多两条待生成提示词（回头、停下姿势）。`assets_src/prepare_art.py` 保留 codex_claude 的最新版本。

## 没有合入的内容

- claude 线的 `husky_view.c/h` 和 `husky_art.h` 另一套渲染实现，留在 `husky_sled_race_claude` 仓库。
- 原 main 工作区的热情值玩法草稿（`app_game.c/h` 改动和 `sled_track.c`），留在本仓库的 stash `backup: main wip before v1.0.0 merge` 里，`git stash list` 可见。
- 各 dev 仓库 `test_artifacts/` 下的日志、录屏 gif、coredump 和设备证据，按 `.gitignore` 约定不进版本库，只保留 `test_artifacts/check_animation.py`。

## 两份计划的共识和待定项

共识部分，v1.0.0 已按此执行：

- 第一人称雪橇视角，六只狗三排成对，蓝调雪林加暖黄路灯。
- 画面纯粹，先把狗跑得欢快做扎实：步态错落、牵引绳、扬雪、镜头随转弯和速度变化。
- 素材用 AI 源图加脚本裁切打包，生成数据提交进仓库。

待定部分，留给 v1.1 以后在本仓库继续：

- 热情值规则、风雪分档和分数公式（claude 计划草案，数值未定稿）。
- 操控接入：交互子板左右键和 IMU 倾斜两套模式，开局可切换，触屏和 Host 键盘兜底。
- 三圈计时、结算和最佳记录存储（NVS）。
- 跳跃、刹车、冰面和甩尾在纯奔跑定位下的取舍。

## 验证状态和下一步

- 合入时已过 pre-commit 全部检查。
- 运行时代码来自已在 dev 线做过模拟器和真机循环验证的一版，本仓库合入后仍需重新跑一次模拟器和真机验收，再确认 `v1.0.0` 标签对应的实际画面。
- 下一步建议顺序：先在本仓库跑通模拟器和真机验收，然后按待定项顺序细化玩法，从操控接入开始。
