# 原版棋盘美术

Mild Mile 中场插画、起点、领奖台和数字使用规则书第 10、11 页嵌入的印刷图。Wild Wilds 中场与特殊格使用第 10 页的棋盘图。来源图保存在 `docs/mildmile-print-left.png`、`docs/mildmile-print-right.png` 和 `docs/wildwilds-print-board.png`。36 张 `racer-tokens`、星形分值筹码及金杯/银花环分值筹码也从第 10 页提取。格子、圆角边框、白色轮廓和折痕由 Canvas 重绘；Three.js 保留实体棋盘厚度、立体角色、骰子和阴影。

`trackLayout.ts` 是印刷层、2D 棋子与 3D 棋子共用的坐标来源：起点占上边三个格宽，1–12 格沿上边，13–14 格沿右边，15–29 格沿下边，30 为左侧领奖区。特殊格编号与服务端 `build_wild_wilds` 一致。

重新生成素材（需要 Python 3、Pillow、NumPy）：

```sh
python3 apps/web/scripts/build-board-atlas.py
```

生成 `apps/web/public/assets/boards/print-atlas.webp` 和 `apps/web/src/components/race3d/boardAtlas.json`。两张地图共用一份图集，运行时不依赖 Python。加载失败时保留带特殊格文字的简化棋盘。

启动前端开发服务后，打开 `/MagicalAthleteOL/race3d-preview.html`。可切换两张地图、立体/俯视视图以及棋子显示。比赛以全屏三维场景展示，竖屏默认显示局部棋盘。镜头平滑跟随移动、技能和待选决策，也可切换到全局视角。比分、掷骰和镜头控制悬浮显示，角色卡可展开查看。预览提供移动和技能特写按钮。

印刷层现使用说明书中的高分辨率素材；格子、边框和折痕继续由运行时绘制。
