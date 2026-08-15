# I Wanna (Python)

Python + [pygame-ce](https://pygame-ce.github.io/) 实现的 **类I Wanna游戏引擎**（含可视化地图编辑器）。

## 特性

- 🎨 **可视化地图编辑器**：三栏布局、图层/撤销/网格（32/16/8px 像素级放置）/自定义材质/背景/音乐/路径节点移动系统/一键测试
- 📦 **打包发布**：编辑器内一键打包单文件 exe（无黑窗、自定义标题/图标、存档在 exe 旁）

## 快速开始

```bash
pip install -r requirements.txt
python main.py              # 启动游戏
python main.py --editor     # 启动可视化地图编辑器
```

退出：`ESC`。素材缺失时自动用占位图，控制台会报告缺失清单。
要新建房间，在\rooms复制一份已经存在的房间，再清空地图进行制作。
\rooms带有一些演示关卡，可以自由删除。

## 按键绑定

| 按键 | 作用 |
|---|---|
| `←` `→` / `A` `D` | 左右移动（立即响应，无惯性） |
| `↑` `↓` / `W` `S` | 普通模式：按住 `↑` 屏蔽跳跃（`Shift+↑` 无反应）；藤蔓上：按 `↑`/`↓` 自然下滑 |
| `Shift` | 跳跃（一段/二段、长短跳）；藤蔓上配合方向键攀爬/跳出 |
| `R` | 死亡后复活 |
| `S` | 在 Checkpoint 处存档（写 `save/save.json`，重开游戏继续） |
| `Z` | 射击子弹（子弹也能碰到 Checkpoint 存档） |
| `F1` / `H` / `Tab` | 碰撞箱可视化 |
| `F2` | 隐藏参数面板（独立小窗口） |
| `ESC` | 退出 |


## 地图编辑器

```bash
python main.py --editor
```

三栏布局：左侧工具面板（工具/网格/图层）、中间 800×608 画布、右侧设置面板。窗口标题栏实时显示：游戏标题 + 游玩时长 + 死亡次数。

| 操作 | 作用 |
|---|---|
| 左键 / 右键 | 放置 / 擦除当前工具（按钮点击带音效 `sndCherry.wav`） |
| 网格按钮 | 32/16/8px：32px 元素吸附格；16/8px 时**所有元素按像素定位**（砖块可放 16px 偏移等） |
| 图层 | 地形/危险/平台/物体/水 五层：V 显示隐藏、L 锁定（存 `editor_layers.json`） |
| `Shift+拖拽` | 连续放置（一次拖拽 = 一步撤销） |
| `Ctrl+Z` | 撤销 |
| `Enter` | 自动保存并测试当前房间（出口目标输入框聚焦时回车 = 应用目标） |
| 材质面板 | 给每种 object 换自定义材质（可细到子类型，如 `tile:block_3`） |
| 路径节点 | 画移动轨迹：与节点重合的元素沿轨迹往复循环移动（速度/触碰触发可设） |
| 背景面板 | 背景色/图片/填充模式/缩放视口框，画布实时预览 |
| 音乐面板 | 房间 BGM + 全局默认音乐（死亡淡出/复活续播） |
| 存工程 / 载工程 | 备份/恢复关卡内容（rooms/music/背景/材质 + 项目设置） |
| 打包 | PyInstaller 单文件 exe：无黑窗、自定义标题/图标、素材内置、**存档在 exe 旁 `save/`** |

工具：砖块(block_0..8)、小砖块(16×16)、尖刺/小刺(四方向)、藤蔓、水(三种)、单向平台、Checkpoint、出口、终点、跳跃球、跳跃星星(1/2/3段)、路径节点、出生点、橡皮擦。

保存后可用 `python tests/room_audit.py` 校验关卡（出生安全/出口目标/存档点可站立）。

## 关卡格式（Room JSON）

```json
{
  "name": "room001",
  "width": 800,
  "height": 608,
  "bg_color": [135, 206, 235],
  "bg_image": null,
  "tiles":       [{"tx": 0, "ty": 18, "type": "block_0"}],
  "spikes":      [{"tx": 12, "ty": 17, "dir": "up"}],
  "mini_spikes": [{"tx": 2, "ty": 17, "dir": "up", "quad": 0}],
  "vines":       [{"tx": 11, "ty": 14, "side": "right"}],
  "platforms":   [{"px": 352, "py": 384}],
  "water":       [{"tx": 6, "ty": 16, "type": "first"}],
  "start":       {"x": 96, "y": 523},
  "checkpoints": [{"tx": 10, "ty": 16}],
  "exits":       [{"tx": 24, "ty": 17, "target": "room002"}],
  "end":         {"tx": 22, "ty": 16},
  "plus_jumps":  [{"tx": 15, "ty": 10}],
  "stars":       [{"tx": 8, "ty": 16, "level": 3}]
}
```

- `tx/ty` 为网格坐标（像素 = 坐标 × 32）；`start` 为 Kid 碰撞箱左上角像素坐标
- **细网格像素元素**（16/8px 放置生成）：`free_tiles`/`free_spikes`/`free_vines`/`free_water` 用 `{"x","y",...}` 像素坐标；`free_checkpoints`/`free_plus_jumps` 为 `{"x","y"}`；`free_exits` 为 `{"x","y","target"}`；`free_end` 为 `{"x","y"}`；`free_stars` 为 `{"x","y","level"}`；`small_tiles` 为 16×16 小砖块
- `bgm` 房间背景音乐（`music/` 下）；无 bgm 的房间自动播「默认音乐」（`editor_settings.json`）
- `textures` 自定义材质：键可细到子类型（`tile:block_3`、`water:first`、`star:2`、`checkpoint:active` 等），粗粒度键（如 `tile`）兜底所有子类型
- `path_nodes` 路径节点：`{"x","y","path":[[x,y],...],"speed","trigger"}`，与节点区重合的元素沿轨迹往复移动
- `bg_image`/`bg_mode`/`bg_zoom`/`bg_offset`：背景图与填充（拉伸/填充/适应/平铺/居中/缩放）

> 加载优先级：`load_room` 先读 `rooms/{name}.json`，缺失/解析失败回退内置测试房。

## 项目结构

```
├── main.py              # 入口（游戏 / 编辑器 / 水测试）
├── config.py            # 集中参数（物理/玩家/地图/按键/演出/目录）
├── core/                # app/assets/input/game/effects/gif/sound/save/settings/pack/bgrender/textures
├── entities/kid.py      # 玩家：11×21 碰撞箱 + 11 步帧物理
├── physics/collision.py # 离散 AABB 碰撞 + 站立探针
├── levels/              # Room 数据模型 + JSON 存取
├── editor/              # 可视化地图编辑器
├── tests/               # 全量回归测试（无头）
├── assets/              # 素材（characters/tiles/spikes/objects/backgrounds/textures/ui）
├── sound/               # 音效（.wav）
├── music/               # 背景音乐（房间自定义 BGM）
├── rooms/               # 关卡 JSON
└── save/                # 持久化存档（运行生成，不入库）
```

## 测试

```bash
python tests/physics_test.py        # 帧级物理回归
python tests/test_vine_jump.py      # 藤蔓跳出/二段跳
python tests/test_vine_oneway.py    # 藤蔓单向通道
python tests/test_water_jumps.py    # 水跳跃语义
python tests/test_jump_star.py      # 跳跃星星
python tests/test_plus_jump.py      # 跳跃球
python tests/test_platform_reset.py # 摸板子重置
python tests/test_music.py          # 背景音乐（淡出/续播）
python tests/test_path_node.py      # 路径节点移动系统
python tests/test_pack.py           # 存工程/打包
python tests/editor_smoke.py        # 编辑器冒烟
python tests/room_audit.py          # 关卡审计
python test_mini_spike.py           # 小刺
```

## 素材说明

素材放 `assets/` 下对应目录，缺失自动用占位图并在启动时报告：

| 分类 | 文件 |
|---|---|
| Kid 动画 | `characters/kid/{anim}_{帧}.png`（idle/run/jump/fall/on） |
| 砖块 | `tiles/block_0.png` ~ `block_8.png` |
| 尖刺/小刺 | `spikes/spike_{dir}.png`、`spikes/mini_spike_{dir}.png` |
| Checkpoint | `objects/checkpoint_0/1.png`（未存档/存档后） |
| 藤蔓 | `objects/tengwan_left/right.png` |
| 子弹 | `objects/bullet_0/1.png` |
| 其他 | `objects/head.png` `platform.png` `plusjump.png` `star_0/2/3.png` `water_{first,second,zero}.png` `end.png` |
| UI | `ui/death.png` `ui/win.gif`（动图，内置纯 Python GIF 解码器） |

音效在 `sound/`：`sndDJump`（跳）、`sndDeath`（死亡）、`sndShoot`（射击）、`snditem`（存档/跳跃球）、`sndwallum`（藤蔓跳出）、`sndBlockChange`（星星）、`sndCherry`（编辑器点击）。

## License

见 [LICENSE](LICENSE)。
