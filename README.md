# BSAI-llama.cpp

BSAI 全家桶 · ComfyUI 本地 llama.cpp 推理插件（最小实现）

> **BSAI-llama.cpp** is a minimal ComfyUI plugin that wraps the official llama.cpp
> prebuilt binaries (`llama-cli.exe` / `llama-server.exe`) for local GGUF LLM
> inference. The 725 MB binary bundle is distributed via Quark Netdisk (夸克网盘);
> this repository contains plugin code only.

---

## 1. 下载二进制 / Download binaries (725 MB)

二进制包（llama-cli / llama-server 等 56 个文件，含 CUDA 12 运行时）由夸克网盘分发：

**夸克网盘下载链接：** https://pan.quark.cn/s/32be06b9c764（文件夹「BSAI-llama.cpp」，约 557 MB zip）

**下载后：** 将压缩包内全部文件解压到插件目录，最终目录结构应如下：

```
ComfyUI\custom_nodes\BSAI-llama.cpp\
├── __init__.py          ← 插件入口（本仓库提供）
├── nodes.py             ← 推理节点（本仓库提供）
├── llama-cli.exe        ← 二进制包内容（夸克网盘下载）
├── llama-server.exe
├── llama.dll
├── ggml.dll
└── ... (共 56 个文件)
```

> 下载后 llama-cli.exe 与其余 dll/exe 必须与 `__init__.py` 同目录，节点才能找到引擎。

---

## 2. 安装 / Install

1. 克隆仓库到 ComfyUI 自定义节点目录：

```bash
cd ComfyUI\custom_nodes
git clone https://github.com/xm6018924/BSAI-llama.cpp.git
```

2. 从夸克网盘下载二进制包，解压到 `BSAI-llama.cpp\` 目录（与 `__init__.py` 同目录）。
3. 重启 ComfyUI。

---

## 3. 节点 / Node

### BSAI Llama Text Gen (llama.cpp)

本地 GGUF 文本生成节点。调用 `llama-cli.exe` 单轮生成，无云端依赖。

| 参数 | 类型 | 说明 |
| --- | --- | --- |
| prompt | STRING | 生成提示词（多行） |
| model_path | STRING | 本地 GGUF 模型绝对路径（用户自备） |
| n_predict | INT | 最多生成的 token 数（默认 256） |
| temperature | FLOAT | 采样温度（默认 0.7） |
| n_ctx | INT | 上下文窗口长度（默认 2048） |
| timeout_sec | INT | 子进程超时秒数（默认 300） |
| extra_args | STRING (可选) | 附加 llama-cli 参数，如 `--top-p 0.9 --repeat-penalty 1.1` |

**输出：** `text`（STRING）— 模型生成的文本。

---

## 4. 模型准备 / Model

节点只负责推理，模型（GGUF）需用户自行准备，常见来源：

- Qwen3 / DeepSeek / Llama 3.x 等官方 GGUF（HuggingFace `ggml-org` 或各量化作者发布）
- 自行用 `llama-quantize.exe` 量化

模型文件放任意路径，在节点 `model_path` 填入绝对路径即可。

---

## 5. 英文说明 / English Quick Start

1. Clone into `ComfyUI\custom_nodes\`.
2. Download the binary bundle from Quark Netdisk (link above) and extract it into
   the plugin folder so `llama-cli.exe` sits next to `__init__.py`.
3. Restart ComfyUI, then use the **BSAI Llama Text Gen** node with a local GGUF model path.

---

## 6. 多代显卡引擎 / Multi-generation GPU engines

三档引擎，按“显卡算力 + 驱动版本”自动选，结果写进 `engine-selection.json`：

| 目录 | 后端 | 覆盖算力 | 最低驱动 | 体积 |
|---|---|---|---|---|
| 插件根（默认） | CUDA 13.0 | sm_86 / 89 / 120 / 121 | 580.65 | 已随包 |
| `engine-cuda12\` | CUDA 12.4 | sm_50 / 61 / 70 / 75 / 80 / 90 | 525.60 | ≈660 MB |
| `engine-vulkan\` | Vulkan | 任意（与算力无关） | 470 | ≈40 MB |

> 注意：官方 CUDA 12.4 构建的 cubin **只编译到 sm_90，不含 sm_86 / sm_89**。
> 所以 30 系（sm_86）的可用性取决于驱动：驱动 ≥ 580.65 走根目录的 CUDA 13 构建（实测 8B Q4
> pp 963 / tg 38.4 t/s），驱动不够时才落到 `engine-vulkan`——它能加载、能出字，但本机实测解码
> 只有 0.73 t/s（比纯 CPU 的 3.84 t/s 还慢），只能算“先让它能跑”。**30 系建议直接升驱动。**
> 另外 NVFP4 / `.ninfer` 量化在 Ampere 没有对应算力，30 系请使用 GGUF 权重。

选型结果同样被 Flint（8082）、Nemotron（8085）和模型管理器读取，不需要分别配置：

```
BSAI-llama.cpp\
├── llama-server.exe …      ← CUDA 13 构建（默认）
├── engine-cuda12\          ← CUDA 12.4 构建（20 系 / 16 系 + 中版本驱动）
├── engine-vulkan\          ← Vulkan 构建（30 系旧驱动 / 算力未覆盖时兜底）
├── bsai_engine_select.py   ← 选型器（nvidia-smi 算力 + 驱动 → 选目录）
├── engine-matrix.json      ← 各引擎探测出的能力表（自动生成）
└── engine-selection.json   ← 当前选中的引擎（自动生成，可手工改）
```

手动切换：

```bat
python bsai_engine_select.py --engine auto            :: 恢复自动（按算力/驱动）
python bsai_engine_select.py --engine engine-vulkan   :: 30 系旧驱动可强制走 Vulkan
python bsai_engine_select.py --engine engine-cuda12   :: 强制 CUDA 12.4 构建
python bsai_engine_select.py --show                   :: 只打印探测结果，不改配置
```

`engine-cuda12\` 与 `engine-vulkan\` 不随 git 分发：同目录执行 `下载CUDA12引擎.bat`
即可从官方 b12224 版本（经 gh-proxy 镜像）把两档一并补齐（已存在则跳过）。

---

## License

MIT（本仓库代码部分）；llama.cpp 二进制版权归 llama.cpp 项目所有（MIT）。
