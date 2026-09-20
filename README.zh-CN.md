# LOVA

[English](README.md) · **中文**

**一门 AI 原生的整数序列编程语言。**

**主页：** [npcnpc09.github.io/lova-lang](https://npcnpc09.github.io/lova-lang/) —— 一页讲完这门语言，铺在二十五万颗粒子之上（`docs/`）。

*状态：**1.0 —— 语言已完整，初步可用。**
十条设计公理全部在语言内部实现，并各有一个实验度量。64 个操作符的表已经用完（63 个操作符加 `END`）：整数、列表、字符串、闭包、`letrec`、循环、可捕获可抛出的错误处理、带血统的程序值、会演化的种群、在声明的能力边界之下的文件 / 时钟 / 网络 IO，以及一个持久化映射。有一个带五个静态趟的编译器、一个类型约束的生成器、一个用 LOVA 写的标准库、模块、命令行、给智能体用的 MCP 服务器，和 1 104 个测试。参考实现是一个只依赖标准库的 Python 解释器；程序跑在一个原生 Rust 运行时上 —— 字节码虚拟机，每秒 1 000 万到 1 200 万步，在一个 1 023 条记录的黄金集上与解释器逐步核对 —— 这是默认运行时，同一个运行时还能作为扩展类装进 Godot 4，于是一个游戏的规则可以是 LOVA，画面是引擎自己的。它没有浮点数，没有命名空间，没有并发。下面"LOVA 还做不到什么"一节如实保留。*

## 一段话的说法

LOVA 只有一个目标：**AI 用它比用任何别的语言都更顺手。** 不是更密，不是更怪：从写到跑对，尝试次数更少；每次失败，花掉的上下文更少；安全地运行代码不需要脚手架；写过的代码能被后来的程序复用、修补和追溯。错误模型、契约、声明式效应、血统和演化机制都是为此而存在的；底下的整数编码是程序的格式和身份，不是重点。**AI 是第一等的读者、作者和执行者** —— 与它一起工作的人排第二。

```lova
(defn square [n] (⊗ n n))
(square 7)
```

……这是一个第一阶段的*投影*。程序本身是一个整数序列；文本是它的漂亮打印。`⊗` 就是 `mul`，`defn` 脱糖成 `let` + `lambda`，调用脱糖成 `apply` —— 所以基底真正存的是：

```lova
(let 0 (lambda 1 (mul (ref 1) (ref 1))) (apply (ref 0) 7))
```

标识符在解析时被驻留为整数名字 id，打印回来也是整数，因为整数才是程序（公理 1）。上面每一种形式都编译到现有的 64 个操作符；语法糖不增加语义。

## 三个阶段

| 阶段 | 表面形式 | 状态 |
|---|---|---|
| **1 —— 文本表面的 LOVA** | 类 Lisp 的 s 表达式，1:1 编译到 token | **当前**，现已面向审计 |
| **2 —— AI 为主的 LOVA** | 一个字符一个字节，没有分隔符（`core/surface2.py`） | **表面已建成并度量**（实验 14）；微调模型仍在 M8 |
| **3 —— 纯 AI 的 LOVA** | 没有文本；程序就是整数序列，人通过 `(explain program)` 阅读 | 北极星 |

## 实际已实现的东西

- **64 token 的核心指令集**（8 族 × 8），每个操作符 1 字节 —— 52 个操作符有运行时语义，12 个保留（`spec/tokens.md`，由 `spec/generate_tokens_md.py` 从表生成）
- **数据** —— 一个 cons 单元（`nil` / `cons` / `head` / `tail` / `nil?`）给出序对、列表，以及作为码点列表的字符串，所以 `"abc"` 是表面语法糖，不占 token 表一个格子（`spec/token-budget.md`）
- **两种表面** —— 第一阶段的 s 表达式用于书写和审计，第二阶段的字节编码投影用于密度：一个字符一个字节，没有分隔符，双向无损（`core/surface2.py`）
- **IO** —— `stdout` / `stdin`，第一批触碰外界的操作符；语言里唯一的非确定性，`static_analyze` 会报告它
- **一个用 LOVA 写的标准库** —— `lib/prelude.lova`：`map`、`filter`、`fold`、`range`、`append`、`reverse`、`digits`、`println` 等等，没有一个是内建。引入是免费的：编译器的 `drop-unused` 趟把一个不调用它们的程序从 474 个节点收回到 1 个
- **命令行** —— `lova run | repl | emit | analyze | mcp`（`core/cli.py`）
- **MCP 服务器** —— `lova mcp` 通过 stdio 向任何 Model-Context-Protocol 宿主提供 `lova_execute`、`lova_static_analyze`、`lova_valid_next` 和 `lova_emit`，标准库之外零依赖；`lova_valid_next` 就是作为服务的公理 3（`core/mcp_server.py`）
- **一种错误模型，从内部可达** —— 每个故障携带同一种结构化异常，`(when-anomaly body handler)` 把异常的代码交给程序，让它能恢复。基底的终止上限是程序唯一不能掩盖的东西
- **种群** —— 语言里的公理 6：`(defpop scorer p1 p2 …)` 建一个池，`(evolve pop)` 用 Python 引擎同样的规则跑一代，`(select pop 0)` 取最适者，赢家能说出自己从哪来。实验 15 把自愈实验重跑成一个 LOVA 程序
- **程序即值** —— `quote` / `eval`，以及整个 Meta 族：`(explain p)` 把程序渲染成文本，`(hash p)` 给出它的整数，`(why p)` / `(lineage-query p)` / `(ancestor-of a b)` 问它从哪来，`(clone p)` / `(mutate p 30)` 派生一个并记下经过，`(read text)` 是 `explain` 的逆，于是程序可以从文本构造程序再 `eval`。公理 5 现在在语言内成立，第三阶段的 `explain` 已经存在
- **世界，需声明** —— `(boundary "fs-read clock" body)` 说明 `body` 可以用哪些效应；`fs-read` / `fs-write` / `clock` 就是效应。编译器拒绝在未声明的边界之外使用，运行时拒绝宿主未授予的边界（`lova run --allow fs-read,clock`），默认什么都不授予，生成的程序不声明就用不了外界。网络是 UDP 数据报上的 `net-send` / `net-recv`：程序声明种类，宿主指定地点（`--allow net=host:port`、`net=:port`）。这是触碰外界的效应上的公理 4
- **一个程序站得住的标准库** —— 迭代而非递归的列表（`len` / `map` / `filter` / `fold` / `sort` / `take` / `zip` ……）、文本（`words` / `lines` / `split` / `join` / `parse-int` / `text-of`）、一个持久化**映射**（`map-put` / `map-get` / `map-pairs`，键是整数或文本），还有 `signal`，让库能抛出调用者可以捕获的结构化异常。`apps/wordfreq.lova` 是验收程序（M22）
- **库** —— `(use "evolution")` 引入 `lib/evolution.lova`，其中一条自定义演化规则用六个 Evolution 操作符写成九行；`(use "prelude")` 是标准库，命令行默认加载。引入是文本式的，只一次，`drop-unused` 之后免费
- **抽象** —— 带柯里化的一元闭包、`letrec`，和一个循环组合子，所以递归和无界迭代都能表达。两个常开的上限（`MAX_CALL_DEPTH`、`MAX_STEPS`）把不终止变成结构化异常，而不是挂起（`core/runtime.py`）
- **类型导向的生成** —— 对任何部分程序，良类型的下一个 token 集合都可计算，所以坏类型的程序不可表示（`core/types.py`、`core/generator.py`）
- **守恒作为类型** —— 预算 / 效应界限写在签名里；违反是编译错误或运行时 Δ 陷阱（`core/conservation.py`）
- **惊异取代栈回溯** —— 偏差以结构化异常浮现；Δ 陷阱扫描器定位最深的出错子表达式*以及*修正值（`core/runtime.py`）
- **血统** —— 每个制品携带来源，可在语言内查询（`core/lineage.py`）
- **种群** —— 一个函数是一池互相竞争的变体，不是单一定义（`core/populations.py`）
- **编译器** —— 作用域检查、类型检查、常量折叠趟；编译错误与运行时异常共用一种模式，智能体只需一个错误处理器（`core/compiler.py`）
- **LOVABench** —— 5 个类别 60 个任务 / 180 个用例，带参考评估器（`corpus/`）。注意：所有任务都早于 M9，没有一个涉及递归或迭代（Q33）。

## 快速开始

需要 Python ≥ 3.10。核心**零依赖**，所以在 PyPy 下同样能跑。装了 Rust 的话，在 `native/lova-rt` 里 `cargo build --release` 构建原生运行时 —— 每秒 1 000 万到 1 200 万步，CPython 的二十倍 —— `lova run` 会对它实现了的每个程序自动使用它（`--native off` 用 Python 运行时，`--native on` 则会告诉你为什么没能用上）：同样的值、同样的异常、同样的步数，逐条对照 `corpus/golden/` 核过。编译好的程序缓存在 `$LOVA_CACHE` 下，Windows 上是 `%LOCALAPPDATA%\lova\cache`，别处是 `~/.cache/lova`，键由源码、它用到的库和实现的哈希组成，所以引入 3D 库的程序第二次运行会跳过一到两秒的解析；`LOVA_CACHE=off` 关掉它。

```bash
git clone <this-repo> lova && cd lova
export PYTHONPATH="$PWD"

# 运行一个程序
python -m core.cli run apps/is_prime.lova 1999      # => 1
python -m core.cli run apps/palindrome.lova racecar # => 1
python -m core.cli run apps/palindrome.lova 's="7"'  # 带引号的参数是文本，即使是 "7"

# 跟一个永远不输的负极大值搜索下井字棋
python -m core.cli run apps/tictactoe.lova 0

# 在预算下运行不可信程序，一行一个；按名字报告每一个
python -m core.cli run apps/sandbox.lova 5000 < programs.txt

# 把一池程序朝一个目标演化，然后问赢家它为什么存在
python -m core.cli run apps/evolve.lova 42 60

# 修复一个违反契约的程序，由惊异引导
python -m core.cli run apps/repair.lova 42 30 200

# 一个 Python 网页壳，唯一的决策是一条你可以随手改坏的 LOVA 规则
python apps/shell/policy_app.py       # http://127.0.0.1:8765

# 坦克大战：窗口是 Python，游戏的每条规则都是 LOVA
python apps/tanks/tank_game.py        # 方向键移动，空格开火
python -m core.cli run apps/tanks.lova 7   # 同一个游戏，在终端里一回合一回合地玩
python apps/g2048/game2048.py 7       # 2048，从 gabrielecirulli/2048 移植
python apps/platformer/platformer.py  # Kenney 的 3D 平台跳跃套件，从 GDScript 移植
python apps/fps/fps.py                # Kenney 的 FPS 套件：两把枪，四个飞行敌人
#   上面两个套件在装了 pygame 时用 SDL 窗口绘制
#   （`pip install pygame` 得到流畅的窗口；Tk 是回退，
#   `--host tk` / `--host sdl` 选择。`--bench N` 打印帧时间）
python apps/godot/fps/build.py path/to/Starter-Kit-FPS --run   # FPS 套件的规则跑在 Godot 里

# 一个交互式会话，已加载标准库
python -m core.cli repl

# 把程序看成第二阶段表面、字节，或一个整数
python -m core.cli emit apps/coprime.lova 14 15 --form stage2
python -m core.cli emit apps/coprime.lova 14 15 --form int

# 不运行，看这个程序会做什么
python -m core.cli analyze apps/collatz.lova 27

# 运行程序自己声明的示例
python -m core.cli check apps/tictactoe.lova 0

# 运行测试套件（1 104 个测试，只用标准库的 unittest）
python -m unittest discover -s tests

# 在 PyPy 下同样，整个套件也应通过
pypy -m unittest discover -s tests -t .

# 运行一个实验
python experiments/experiment_01_hello_lova.py

# 每个应用的 Python 驱动仍然可用，并打印完整流水线
#   （解析 → 分析 → 编译 → 编码 → 求值）
python apps/is_perfect.py 28
```

或者安装它 —— wheel 打包了核心、LOVA 库和语料，并把 `lova` 命令放到路径上：

```bash
pip install .
lova run apps/is_prime.lova 1999
```

### 交给智能体

`lova mcp` 在 stdin/stdout 上说 Model Context Protocol。任何 MCP 宿主 —— Claude Code、Claude Desktop、Cursor —— 得到四个工具：运行程序（带显式的能力授予）、不运行地分析程序、问一个部分程序接下来可以是哪些 token，以及把程序投影成第二阶段 / 字节 / 一个整数。

```json
{"mcpServers": {"lova": {"command": "lova", "args": ["mcp"]}}}
```

不安装、直接从检出目录用：`"command": "python", "args": ["-m", "core.cli", "mcp"], "cwd": "/path/to/lova-lang"`。`apps/mcp_demo.py` 通过管道驱动服务器，每个工具各调用一次。

全部 14 个实验都能跑。实验 03 和 07 自语料从 20 个任务扩到 60 个之后就失效了；在 M13 修好，下面它们的数字是 60 任务的。

实验 11 另外需要 `tiktoken`：

```bash
pip install -e ".[experiments]"
```

## 这些程序说明了什么

`apps/` 里有二十三个程序，每一个都是为了拿这门语言做点什么而写的，并留作测试。它们展示的是：

- **它能跑游戏。** 坦克大战，实时：八个敌人沿网格顶部到来，四处游荡，直到沿一条无遮挡的直线看见你或你的基地，然后开火。每条规则 —— 移动、子弹能打穿的墙、敌人的瞄准、生成、胜利 —— 都是 `lib/tanks.lova`，大约 250 行作用在一个世界记录上的纯函数，自带十八个由 `lova check` 运行的示例。窗口是 tkinter，只拥有像素和按键：每秒十次，它把世界和你按住的键交给 LOVA 程序，拿回下一个世界，画出来。一回合大约 10 000 步，预算 200 000，显示在角落；一条跑飞的规则会成为屏幕上的结构化异常，而不是冻住的窗口。同一套规则在终端里逐回合可玩。

  ![坦克大战：窗口是 Python，每条规则都是 LOVA](apps/tanks/screenshot.png)

  ```bash
  python apps/tanks/tank_game.py             # 方向键移动，空格开火，R 重开
  python -m core.cli run apps/tanks.lova 7   # 终端
  ```

- **它能移植别人的游戏，并证明移植是对的。** 2048，源自 [gabrielecirulli/2048](https://github.com/gabrielecirulli/2048)（MIT）：`lib/g2048.lova` 对着原版的 `js/game_manager.js` 写成 —— 同样的遍历顺序、同样的最远位置行走、同样的"本步合成过的方块不能再合"规则、同样的计分、同样的九成出 2 的概率。"移植的行为和原版一样"这个断言不是用散文说的：`tests/test_2048.py` 里有原版的 Python 转写，两者在随机局面上一起跑，逐格比对棋盘。**10 000 个局面，零分歧。** 一处有意的不同 —— 原版的随机是 `Math.random`，不可重放；这里生成器穿过世界传递，所以一个种子就是一局。这次移植还在我们自己的编译器里找到一个真 bug，在 `drop-unused` 对因副作用而保留的绑定的处理上。

  ![2048：窗口是 Python，规则是 LOVA](apps/g2048/screenshot.png)

  ```bash
  python apps/g2048/game2048.py 7            # 窗口，用原版的配色
  python -m core.cli run apps/g2048.lova 7   # 终端
  ```

- **还有一个 3D 平台跳跃，从 Kenney 的入门套件移植。** `lib/platformer.lova` 装着 [KenneyNL/Starter-Kit-3D-Platformer](https://github.com/KenneyNL/Starter-Kit-3D-Platformer)（MIT，约 1 200 星）的规则，对着它的 GDScript 写成：会走、二段跳、落地压扁的角色，上下浮动旋转的金币，会塌的平台，从下面顶碎的砖，跟随、转向、缩放的相机，以及掉出世界后一切重来 —— 每个常量都是套件自己的。`lib/scene3d.lova` 把套件的模型放进一个可移动相机下的画面：四十六个物体被摆放、旋转、倾斜、剔除、打光，**每 tick 约 4 000 步 LOVA，每帧约 150 000 步**。模型和关卡是套件的，由 `apps/platformer/import_kit.py` 从它的 `.glb` 文件和场景里读出，各自减面到预算之内，颜色留在原处。`tests/test_platformer.py` 转写了套件的五个脚本，在一段脚本化的游玩中与移植版一 tick 一 tick 并排跑：**每个位置的偏差在四毫米之内**，拿到同样的金币，在同一 tick 掉出世界。

  ![Kenney 的平台跳跃关卡：窗口是 Python，游戏是 LOVA](apps/platformer/screenshot.png)

  ```bash
  python apps/platformer/platformer.py                   # WASD、空格、方向键、+/-
  python apps/platformer/platformer.py --shot out.png    # 一帧，不开窗口
  ```

- **还有一个第一人称射击，来自 Kenney 的 FPS 入门套件。** `lib/fps.lova` 装着 [KenneyNL/Starter-Kit-FPS](https://github.com/KenneyNL/Starter-Kit-FPS)（MIT，约 1 000 星）的规则：一个以 5 的速度行走、二段跳、用鼠标看、开两把枪的玩家，枪的冷却、散布、弹数和后坐都是套件自己的资源；四个沿余弦悬浮、转身面向他、每四分之一秒射出一条五米射线的飞行敌人；用整数做的对球和盒的射线检测；掉出世界后重来。画面从眼睛看出去：`lib/scene3d.lova` 加了第一人称相机，武器握在套件第二个相机握着它的位置，按两个视场角之比。`tests/test_fps.py` 转写了 `player.gd`、`enemy.gd` 和两个武器资源，在一段 642 tick 的脚本化游玩中与移植版并排跑 —— 行走、张望、跳过缺口、把两把枪清空到一个敌人身上、中弹、沿墙滑行、掉下去：**同样的位置在四毫米之内，同样的偏航、俯仰、生命、冷却和敌人，一 tick 不差**。在原生运行时上一 tick 2 毫秒、一帧 8 毫秒，SDL 窗口稳在每秒 60 帧（`apps/fps/README.md` 有表）；两个运行时画出的图逐字节相同。

  ![Kenney 的 FPS 关卡，从眼睛看：窗口是 Python，游戏是 LOVA](apps/fps/screenshot.png)

  ```bash
  python apps/fps/fps.py                                 # WASD、空格、鼠标、E、左键
  python apps/fps/fps.py --shot out.png                  # 一帧，不开窗口
  ```

- **同一套规则，在 Godot 里面。** `native/lova-godot` 是原生运行时作为 Godot 4 扩展类，`apps/godot/fps` 是套件自己的 Godot 工程，其中 `player.gd` 和 `enemy.gd` 换成了每个物理 tick 调用一次 `lib/fps.lova`、把答案写进套件节点的脚本。Godot 画它自己的场景 —— 天空、模型、枪口火光、击中贴图、HUD —— LOVA 决定其中发生的一切，每 tick 0.6 毫秒。**[一段七秒的录像](apps/godot/fps/demo.mp4)**（带声音），由 `build.py --movie` 制作，展示 demo 走进来、环顾四周、用两把武器解决四个敌人中的三个；角落里每 tick 显示规则的开销。

  ![Kenney 的 FPS 套件由 Godot 绘制，每条规则都是 LOVA](apps/godot/fps/screenshot.png)

  ```bash
  cargo build --release --manifest-path native/lova-godot/Cargo.toml
  python apps/godot/fps/build.py path/to/Starter-Kit-FPS --run     # 玩
  python apps/godot/fps/build.py --movie=demo.mp4                  # 录 demo
  ```

- **逻辑第一次就跑对。** 词频统计、游戏、日志汇总、批处理、沙箱：每个程序的逻辑在第一次执行时就给出了正确结果。错误若出现，要么在编译时被抓住并附修复提示，要么在运行时作为结构化异常报告，从来不是崩溃或回溯。
- **失败是数据。** 沙箱运行不可信程序，一行一个，按哈希和值报告每一个，或按故障的*名字*：死循环撞上它的 `budget`，读文件撞上它没声明的边界，不是程序的文本被说成不是程序。没有东西能碰到沙箱，沙箱也不需要任何授权。
- **契约是程序自己的。** 批处理给每个作业各自的预算，数一数超预算的作业有几个；修复器声明一个 `conserve` 契约，对病人反复变异直到契约成立，只保留缩小惊异的变异。300 个作业里 219 个在预算内完成，与外部计算的预测完全一致；三个修复目标分别在 39、37 和 20 次尝试内收敛，可复现。
- **来源可以从内部查询。** 演化的赢家和修复后的程序各自打印自己的文本、代数、存在的理由和血统长度，不借 Python 的手。
- **世界是声明的。** 两个进程交换数据报，一个文件被读，时钟被查，每一样都在一个边界之下，边界说明效应的种类，宿主指定地点。没有声明某个效应的程序碰不到它，编译器在运行之前就会说。
- **程序是整数。** 每一个程序从它的第二阶段投影重跑，输出和值完全相同，那个 3 000 字符的游戏也不例外。
- **一个模型看一页就能写。** 一个新开的 Claude 会话拿到 `corpus/language_card.md` 和 LOVABench v3 的 80 个任务，每题一答、不执行，写对了 **80 题中的 79 题**，与它在同样任务上的 Python 得分完全一样；算法类两边都是 20 题全对。这门语言不让模型多花一分力气去写，却给它的程序带来 Python 没有的契约、预算和结构化故障（`journal/experiment_17.md`）。
- **一个模型能从故障出发修好它。** 在一个新会话运行自己的代码并读取返回结果的循环中，十个带循环、列表和文本的任务：两种语言都十题全对，LOVA 提交了十一次，Python 十次。LOVA 唯一的一次失误是编译故障，附有摘录、行号和该写的替换；下一次提交就通过了。LOVA 的答案作为一次函数调用在预算下运行，什么都不授予；Python 的答案需要一个子进程和一个超时（`journal/experiment_18.md`）。在八个更大的任务上，每种语言三个会话，会话遇到的每个编译故障都在下一次提交修好，会话称诊断"极好"；步数预算现在会报告步数去了哪些函数（`journal/experiment_19.md`）。
- **Python 能跑的地方它都能跑，Rust 能跑的地方它跑得快。** 核心零依赖，所以同样的程序在 CPython 和 PyPy 下都能跑，1 104 个测试两边都通过；原生运行时以每秒 1 000 万到 1 200 万步运行同一串字节，也能在 Godot 里跑。
- **文本是值。** 字符串字面量是一个节点；`words`、`split`、`join`、`parse-int` 等各是一个操作符；一万行的词频统计在 CPython 上从 28 秒降到 5.5 秒（M25）。
- **故障说明在哪，修复就是一个补丁。** 每个异常携带出错表达式的源码范围和文本；MCP 服务器的 `lova_patch` 替换那个范围 —— 或者一个具名 def 里的一段文本 —— 并检查结果。一个失败的 `example` 会说出让它通过的那一处编辑，附替换文本。智能体跑的循环是执行、打补丁、执行，一次修复的代价就是修复本身的大小。
- **程序回答问题，而不是被通读。** `lova_show` 按名字给出一个 def 及其范围和参数，`lova_scope` 给出某一点绑定了什么，`lova_callers` 给出谁调用谁 —— 于是智能体读的是它问到的那个 def，不是整个文件。
- **程序发现的问题当天修好。** 写这些程序暴露了四个边角 —— 输入、自引用、程序 id、参数 —— 每一个在当天结束前都变成了一项编译期检查、一个 prelude 函数或一种命令行形式，每种形状都有测试。日志留有记录。

## LOVA 的位置

每门语言都有自己的位置。Python 是胶水和笔记本，Rust 是系统层，JavaScript 是浏览器，Erlang 是永不宕机的交换机。LOVA 的位置是 **AI 写、机器跑、人不必读的代码**：智能体整天产出的小程序，系统让用户或模型修改的规则和策略，长期运行的服务自己调整的例程。它给这个位置带来的，是一组任何通用语言都不具备的保证。

### 与其他语言对照

| 程序得到什么 | Python | Rust | Haskell | Clojure | Unison | **LOVA** |
|---|:-:|:-:|:-:|:-:|:-:|:-:|
| 故障是结构化数据而不是文本 | – | 部分 | 部分 | – | – | **是** |
| 生成器无法表示畸形程序 | – | – | – | – | – | **是** |
| 效应由程序声明、由宿主授予 | – | – | 类型化 | – | 部分 | **是** |
| 保证终止 | – | – | – | – | – | **是** |
| 程序内部的开销契约 | – | – | – | – | – | **是** |
| 程序是第一等数据 | – | – | – | 是 | 是 | **是** |
| 来源可从内部查询 | – | – | – | – | 部分 | **是** |
| 函数是一个演化中的种群 | – | – | – | – | – | **是** |
| 由程序自身偏差引导的修复 | – | – | – | – | – | **是** |
| 零依赖，一个核心同时跑在 CPython 和 PyPy | 核心 | – | – | JVM | 运行时 | **是** |

LOVA 如何做到每一项，按表的顺序：

1. 每个故障携带种类、位置路径和修复提示，编译时和运行时一样；`when-anomaly` 让程序捕获自己的故障并按代码分支。
2. `valid_next` 在每一步给出合法的下一个 token，所以生成的程序不可能语法错误或作用域错误。
3. `(boundary "fs-read" ...)` 声明效应的种类，`--allow` 指定地点；未声明的效应是编译错误。
4. 步数和深度上限是内建的：永不结束的循环是结构化异常，从不挂起，超预算的运行会说出步数去了哪些函数。
5. `(budget n ...)` 按调用、按作业、按每一行不可信程序；程序捕获自己的超支。
6. `quote`、`eval`、`read`、`explain`、`hash`：程序是一个整数，也是语言处理的一个值。
7. `why`、`generation`、`lineage-query` 是操作符；记录在值里，不在旁路里。
8. `defpop`、`evolve`、`select`：赢家解释自己的血统。
9. `conserve` 声明契约，`surprise` 度量偏差，`mutate` 提出方案；三个目标分别在 39、37、20 次尝试内修好，可复现。
10. 核心只用标准库；1 104 个测试在两个解释器上都通过。

以及支撑"它不让模型多花一分力气"这个说法的度量：一个新开的 Claude 会话拿到一页 LOVA，单次作答写对了 80 个基准任务中的 79 个，与它的 Python 得分完全一样。

其中三项散见于别处：类型里的效应（Haskell、Koka），代码即数据（Lisp、Unison），自愈的系统（Erlang）。没有哪一门同时有这三项，也没有哪一门有另外七项。LOVA 是它们在 64 个操作符里相遇的地方。

### 场景

**智能体的沙箱。** 一个干活的智能体需要不停地计算 —— 求和、变换、检查 —— 今天它把 Python 写进一个容器。在 LOVA 里程序不会挂起，碰不到它没声明的文件或网络，每次失败都作为数据报告。`apps/sandbox.lova` 在预算下一行一个地运行不可信程序，按摘要和值或按故障名报告每一个，它自己只是十二行不需要任何授权的 LOVA。MCP 服务器（`lova mcp`）把这个提供给任何宿主。

**应用的规则层。** 界面、存储和网络用你已经在用的语言；唯一*做决定*的那一块 —— 一条定价规则、一项策略、用户或模型的脚本 —— 用 LOVA，可以在线编辑，在预算下、无任何能力地运行，伤不到承载它的应用。`apps/shell/policy_app.py` 是一个 Python 网页壳，唯一的决策是一条你可以在浏览器里随手改坏的 LOVA 规则；`apps/tanks/tank_game.py` 是一个坦克大战，每条规则 —— 移动、子弹、敌人的瞄准、胜利 —— 都是 `lib/tanks.lova`，由一个只拥有像素和按键的 Python 窗口每秒调用十次。

**必须可审计的生成代码。** 程序是一个携带血统的整数：哪个模型、什么时候、从哪个父代、为什么。`apps/repair.lova` 和 `apps/evolve.lova` 打印出它们产出的程序的血统。在 AI 写的代码上线前必须可追溯的地方，记录在值里，不在旁路里。

**自我调整的例程。** 一个服务的启发式 —— 重试策略、排序权重、阈值 —— 作为一个 `defpop` 种群：变体竞争，输家退役，赢家被克隆和变异，每个版本都能说出自己为什么存在。契约（`conserve`、`budget`）限定演化可以做什么。

**受约束解码的目标。** 对一个必须产出可编译代码的小模型或端侧模型，`valid_next` 就是语法：每一步只提供合法的 token。微调语料（`corpus/finetune.py`，3 000 对经验证的样本）和一页语言卡已经就绪。

LOVA 不适合什么：界面、图形、实时输入、浮点，或者要由人手工维护的代码。这些是它为换取上面那些保证而做的取舍。

## 度量

所有数字都来自 `journal/`；每一个都链接到 `experiments/` 里一个可复现的脚本。这些是**研究规模的结果，不是有统计保证的基准** —— 每一项都标明了样本量。

| 指标 | 结果 | 来源 |
|---|---|---|
| pass@1，同样的任务和同一个 LLM | LOVA 60/60 对 Python 59/60 | 实验 07（LOVABench v2，60 任务，单次运行） |
| 通过的测试用例，同一比较 | LOVA 180/180 对 Python 177/180 | 实验 07 |
| 原始字节密度对 Python，数论任务 | 25.8× | 实验 07（v1 的 20 任务切片报告 39.2×） |
| LLM token 密度对 sympy-Python，数论任务 | 2.0×（少 50% token） | 实验 11b（LOVABench v2，60 任务，tiktoken cl100k_base） |
| LLM token 密度对纯 Python，数论任务 | 8.5× | 实验 11b |
| **LLM token 密度对 Python，算法任务 —— 第二阶段** | **1.13×（更密）** | 实验 14 |
| ……同样的任务，第一阶段 s 表达式表面 | 0.66× —— 第一阶段贵 1.5 倍 | 实验 12 |
| LLM token 密度对 sympy-Python —— 第二阶段，LOVABench v2 | **5.38×** | 实验 14 |
| 第二阶段表面的无损性 | 2150 / 2150 次往返精确 | 实验 14 |
| 字节密度对 Python，算法任务 | 1.19× | 实验 12 |
| 需要递归 / 迭代的任务中 LOVA 能表达的 | 44/44 用例（M9 之前 0/10） | 实验 12 |
| 仅靠操作符*拼写*收窄的算法密度差距 | 30%，**零** token 格子 | 实验 13 |
| ……靠把 `lt` 和 `sub` 加为原语 | 9%，2 个格子 —— 所以它们改作宏发布 | 实验 13 |
| ……任何 token 表改动都够不着的剩余部分 | 61%（s 表达式语法） | 实验 13 |
| 跑飞的程序产生结构化异常 | 5/5，全部带完整的 L2 模式 | 实验 12 |
| 生成程序中的未绑定引用 | 248/1000 → **0/1000**；可运行 29% → 38% | 实验 16（作用域感知的生成，M17 重跑） |
| 自愈，写成一个 LOVA 程序 | 10 个种子中 9 个改善，3 个收敛，最好的 35 → 1 | 实验 15（10 种子 × 30 代） |
| 常量折叠压缩 | 节点少 58.5%，字节少 43.9% | 实验 08 |
| 遥测加权采样对均匀采样 | 无陷阱通过率 +32 个百分点（88% 对 56%） | 实验 10（N=50，M16 用作用域感知采样器重跑） |

### 正确率这个数字实际度量的是什么

60/60 是真的，但比看上去窄。LOVABench 的任务是*用* LOVA 写出来的，v2 的提示把公式直接说了出来 —— "计算 p(tau(sigma(n)))"。所以以 Claude 为预言机的基线度量的是**转写成 s 表达式**，不是程序合成。把它读作"这个表面能被模型写出来"的证据 —— 这值得知道 —— 而不是"模型能用 LOVA 编程"的证据，它没有证明这一点。一个算法语料（Q33）才能度量那个。

### 密度数字实际度量的是什么

把两行密度放在一起读，因为它们不一致，而不一致本身就是发现。

8.5× 来自数论任务，那里 LOVA 程序是 `(sigma n)` —— 一个一字节的内建 —— 而 Python 是一个 import 加一次 sympy 调用。这个比较把功劳记给了语言的标准库。它是对领域塑形的操作符集合的一个真实且站得住的论证，但它不是对写程序的度量。

实验 12 度量的是十个双方都没有捷径、都得把算法写出来的任务：阶乘、斐波那契、素性、Collatz、欧几里得 gcd 等等。在那里 LOVA 的第一阶段表面**比 Python 多花 1.5 倍的 LLM token**，第二阶段投影也救不回来（0.65×）—— `(merge n -1)` 是七个 token，而 `n - 1` 是三个，没有哪个分词器能修好一个在一次减一上花五个 AST 节点的操作符集合。

所以：LOVA 在内建匹配任务的地方很密，在一般算法代码上不如 Python 密。两个数字都留在表里。

实验 13 随后拆解了这个差距，发现表是错误的工具：**第一阶段 token 开销的 51% 是操作符名字，25% 是括号**，所以缩短名字就在零格子的代价下收窄了 30% 的差距 —— 是两个候选新操作符价值的三倍 —— 剩下 61% 是 s 表达式语法，64 个格子怎么分配都够不着。

实验 14 造出了*够得着*它的工具。括号从来就不是必要的：字节编码没有分隔符，因为元数决定结构，所以第一阶段把四分之一的 token 花在重述基底已经知道的事上。第二阶段表面就是用字符写出来的字节序列 ——

```
Stage 1   (defn square [n] (mul n n))(square 7)
Stage 2   W0\1*LL$A7;
```

—— 它把算法代码从 0.66× 带到 **1.13×**，越过了 token 表永远打不破的 0.76× 天花板，把 LOVABench 对 sympy-Python 从 2.00× 带到 **5.38×**。它无损往返 2150/2150。

所以诚实的一句话说法不是"密 8.5 倍"。而是：**LOVA 的第二阶段表面在内建匹配任务的地方比 sympy-Python 密 5.4 倍，在不匹配的地方密 1.1 倍。** 更小，但它经得起显而易见的攻击。

有一件事这*不能*说明：模型能否写第二阶段。`valid_next` 应该让它比第一阶段更容易 —— 没有分隔符可以放错 —— 但这没有测过，是项目承重的开放问题（Q47）。

关于诚实的说明：实验 11 在较窄的 20 任务集上的第一次运行报告 2.5×/13.3×；在更宽的 60 任务 v2 集上重跑降到 2.0×/8.5×。上面引用的是 v2 的数字。NULL、被削弱的，以及 —— 自实验 12 起 —— 干脆为负的结果都有意保留在日志里。

## 仓库布局

```
core/          参考实现（token、类型、运行时、守恒、血统、种群、编译器、遥测）
spec/          设计文档 —— 公理、token 表、范式继承
corpus/        LOVABench v3（80 任务）、评估器、微调语料 + 语言卡
experiments/   带编号、可复现的验证脚本
journal/       研究日志 —— 每个实验一条，NULL 也在内
apps/          第一等的 LOVA 程序
lib/           prelude.lova —— 用 LOVA 写的标准库
tests/         1 104 个单元测试，只用标准库
native/        Rust 运行时（lova-rt）和它的 Godot 扩展（lova-godot）
```

## LOVA 还做不到什么

直说，因为清单很短而缺口很大：

- **它不是数据语言。** 原生虚拟机每秒 1 000 万到 1 200 万步，一个游戏的 tick 不到一毫秒；几万行的词频统计要几秒。几百万行，或者想要向量单元的算术，还不是这门语言的事（Q76）。
- **IO 是整值的。** `fs-read` 读整个文件，`net-recv` 收一个数据报：没有句柄，没有流（Q72）。终端是环境的，不是声明的（Q68）。
- **核心表已满，语言在往表外长。** 63 个核心操作符加 `END`；文本族（0x40-0x4F，M25，M32 时满）是 64 之外的第一次扩展，再下一个操作符得挤掉数论族里的一个（Q74）。
- **模块是文本式的。** `(use "name")` 引入 `lib/name.lova`，只一次且传递，`drop-unused` 让它免费 —— 但两个库定义同一个名字时按引入顺序遮蔽；没有命名空间（Q50 在这个限度上关闭）。
- **种群是它自己的值，不是程序列表。** 这暂时绕开了参数化列表（Q42）；`List<T>` 仍是长期更好的形状（Q63）。
- **`head` 在运行时检查。** cons 单元可以装任何值 —— M17 起树和程序列表都可表示 —— 所以 `head` 的结果类型跟着它的列表走，检查器看不见。参数化的 `List<T>` 能找回静态答案（Q63）。
- **参数无类型。** 检查器从 lambda 推断函数的形状 —— 元数和返回类型（M20），所以部分应用或调用结果放错格子是编译错误；但 LOVA 没有参数注解，所以函数体内误用的参数在它的值被使用的地方、在运行时才被抓住（Q43）。生成器仍在 `Fn` 层面工作（Q71）。
- **生成够不到互递归。** M16 起生成状态机保持作用域，所以生成的程序里未绑定或类型错误的引用不可表示（实验 16：704/1000 → 0）。但一个从左到右的机器没法引用后面才绑定的东西，所以一条互递归的 `def` 链 —— M12 起合法 —— 能编译，却不能生成（Q64）。

## 阅读顺序

1. `spec/axioms.md` —— 10 条设计不变量和每一条的论证
2. `spec/paradigm-inheritance.md` —— LOVA 综合的七条编程语言轨迹
3. `spec/tokens.md` —— 64 操作符表
4. `journal/README.md` —— 实验日志
5. `CLAUDE.md` —— 完整的项目导览（为 AI 会话而写）

## 血统

LOVA 的架构词汇 —— PFS、守恒、血统、惊异、演化、Δ 安全 —— 继承自 **DNA OS v3**，同一作者的一个独立（未发表）研究项目。概念是共享的；这里的代码是独立的重新实现，不是分叉。

## 设计哲学

人类可读性是基底明确的**非目标**。第一阶段的文本表面存在的意义是引导项目起步、按需审计程序 —— 它是工具，不是语言。为了让 LOVA 对人更友好而牺牲第三阶段纯整数表示的贡献，将被原则性地拒绝（见公理 10）。

语言里的任何地方也都没有盈亏 / 奖励目标。用户通过守恒契约和惊异预算声明自己的目标；基底只负责强制遵守。

## 许可证

MIT —— 见 [LICENSE](LICENSE)。
