# BSAI-llama.cpp

BSAI 全家桶的本地 llama.cpp 推理插件：用官方预编译二进制跑本地 GGUF，无云端依赖。
A minimal ComfyUI plugin from the BSAI suite that wraps official llama.cpp prebuilt binaries
(`llama-cli.exe` / `llama-server.exe`) for fully local GGUF inference — no cloud calls.

支持多代 NVIDIA 显卡：按 **算力 + 驱动版本** 自动在三档引擎之间选型，30 系（Ampere / sm_86）
不再受“只能跑最新驱动”的限制。本仓库只放插件代码与选型器，二进制走网盘 + 一键脚本分发。
It selects one of three engine builds automatically based on **compute capability + driver
version**, so 30-series (Ampere / sm_86) cards are covered instead of being blocked by the
driver floor of the newest CUDA build. This repository ships code only (plus the engine
selector); binaries come from the netdisk bundle and a one-click script.

---

## 目录 / Table of contents

1. [环境要求 / Requirements](#1-环境要求--requirements)
2. [安装 / Installation](#2-安装--installation)
3. [30 系显卡完整指南 / 30-series (sm_86) guide](#3-30-系显卡完整指南--30-series-sm_86-guide)
4. [节点 / Node](#4-节点--node)
5. [与 BSAI 全家桶协同 / Shared with the BSAI suite](#5-与-bsai-全家桶协同--shared-with-the-bsai-suite)
6. [排障 / Troubleshooting](#6-排障--troubleshooting)
7. [实测数据 / Benchmarks](#7-实测数据--benchmarks)

---

## 1. 环境要求 / Requirements

- Windows 10/11（引擎是 win-x64 构建）/ Windows 10/11, x64
- ComfyUI（任意整合包，Python 3.10+）
- NVIDIA 显卡：CUDA 13 档需驱动 **≥ 580.65**；CUDA 12.4 档需 **≥ 525.60**；Vulkan 档需 **≥ 470**
  NVIDIA GPU: CUDA 13 tier needs driver **≥ 580.65**, CUDA 12.4 tier **≥ 525.60**, Vulkan tier **≥ 470**
- 无 NVIDIA 卡时可退到 CPU 后端（`--ngl 0`），仅慢，不报错
  Without an NVIDIA GPU it falls back to the CPU backend (`--ngl 0`) — slow but functional

查显卡与驱动版本 / Check your GPU and driver:

```bat
nvidia-smi --query-gpu=name,compute_cap,driver_version --format=csv
```

---

## 2. 安装 / Installation

### 2.1 拉代码 / Clone the code

```bat
cd ComfyUI\custom_nodes
git clone https://github.com/xm6018924/BSAI-llama.cpp.git
```

### 2.2 装二进制 / Install the binaries (725 MB)

二进制包（56 个文件，`llama-cli.exe` / `llama-server.exe` / 各 `ggml-*.dll` / CUDA 运行时）
由夸克网盘分发：**https://pan.quark.cn/s/32be06b9c764**（文件夹「BSAI-llama.cpp」，约 557 MB zip）。

The binary bundle (56 files: `llama-cli.exe`, `llama-server.exe`, `ggml-*.dll`, CUDA runtime)
is distributed via Quark Netdisk: **https://pan.quark.cn/s/32be06b9c764** → folder
"BSAI-llama.cpp" (~557 MB zip). Extract **everything** into the plugin folder:

```
ComfyUI\custom_nodes\BSAI-llama.cpp\
├── __init__.py            ← 本仓库 / from this repo（插件入口 + 节点）
├── bsai_engine_select.py  ← 本仓库 / from this repo（引擎选型器）
├── llama-cli.exe          ← 二进制包 / from the bundle
├── llama-server.exe
├── llama.dll / ggml*.dll / cublas*64_13.dll / cudart64_13.dll
└── ... (共 56 个文件)
```

> `llama-cli.exe` 必须和 `__init__.py` 同级，节点才能找到引擎。
> `llama-cli.exe` must sit next to `__init__.py`, otherwise the node cannot find the engine.

重启 ComfyUI 后即可用节点 / Restart ComfyUI and the node is ready.

---

## 3. 30 系显卡完整指南 / 30-series (sm_86) guide

### 3.1 先搞清楚你落在哪一档 / Find your tier first

30 系（3060 / 3070 / 3080 / 3090，sm_86）**能不能用，取决于驱动，不取决于引擎包**：

```bat
python bsai_engine_select.py --show
```

输出里的 `selected` 就是结论 / `selected` in the output is the answer:

| 你的情况 / Your case | 结果 / Result | 需要下载吗 / Download? |
| --- | --- | --- |
| 30 系 + 驱动 ≥ 580.65 | 根目录 CUDA 13 构建，**性能最好** | 不用，随包已有 / nothing |
| 30 系 + 驱动 < 580.65 | `engine-vulkan`（能跑但慢，见 §7） | 需补 Vulkan 档 / Vulkan tier |
| 20 系（sm_75）/ 16 系（sm_61、70）+ 驱动 ≥ 525.60 | `engine-cuda12` | 需补 CUDA 12.4 档 |
| 20/16 系 + 驱动更低 | `engine-vulkan` | 需补 Vulkan 档 |

> **关键事实**：官方 llama.cpp 的 CUDA 12.4 构建，`ggml-cuda.dll` 里只有
> `sm_50 / 61 / 70 / 75 / 80 / 90` 的 cubin，**没有 sm_86、也没有 sm_89**，也没有可用的 PTX。
> 所以 30 系不要指望 `engine-cuda12`——它救不了 30 系，只服务 20 系 / 16 系。
> Key fact: the official CUDA 12.4 build ships cubins for `sm_50/61/70/75/80/90` only —
> **no sm_86, no sm_89, no usable PTX**. So `engine-cuda12` is for 20/16-series, not 30-series.

### 3.2 怎么下载 30 系要用的引擎 / How to get the 30-series engine

**方式 A（推荐）：升驱动，零下载 / Option A (recommended): update the driver, no download**

把 NVIDIA 驱动升到 **580.65 或更高**，30 系直接用根目录那套 CUDA 13 构建，性能最好。
Update your driver to **580.65+** and the bundled CUDA 13 build just works — fastest path.
（驱动 580 及以上覆盖 Ampere / Ada / Blackwell，30 系升完即可用。/ Driver 580+ covers
Ampere, Ada and Blackwell, so 30-series is fine after the update.）

**方式 B：一键补齐两档扩展引擎 / Option B: one-click, adds both extra tiers**

```bat
:: 在 BSAI-llama.cpp 目录下双击，或在 CMD 里执行
下载CUDA12引擎.bat
```

脚本会（幂等，已存在则跳过 / idempotent, skips what already exists）：

1. 从 `gh-proxy.com` 镜像拉官方 **b12224** 三个包（CUDA 12.4 主体 + cudart + Vulkan，约 700 MB）；
2. 解压到 `engine-cuda12\` 和 `engine-vulkan\`；
3. 调 `bsai_engine_select.py --show` 打印当前显卡的选型结果。

**方式 C：只补 Vulkan（30 系旧驱动的最小方案，约 40 MB）/ Option C: Vulkan only**

```bat
mkdir engine-vulkan
curl -L --retry 6 -o vulkan.zip https://gh-proxy.com/https://github.com/ggml-org/llama.cpp/releases/download/b12224/llama-b12224-bin-win-vulkan-x64.zip
tar -xf vulkan.zip -C engine-vulkan
del vulkan.zip
engine-vulkan\llama-server.exe --list-devices
```

`--list-devices` 应打印 `Vulkan0: NVIDIA GeForce RTX 30xx …`，说明后端可用。
It should print your card as `Vulkan0`, which means the backend is usable.

镜像说明 / Mirror note：GitHub 直连常被重置（`curl: (56)`），`ghfast.top` 会 403，用
`https://gh-proxy.com/` 或 `https://ghproxy.net/` 前缀包住原始 GitHub 链接即可。
Direct GitHub downloads are often reset; `ghfast.top` returns 403; prefix the original
GitHub URL with `https://gh-proxy.com/` or `https://ghproxy.net/`.

### 3.3 三档引擎矩阵 / Engine tiers

| 目录 / Dir | 后端 / Backend | 覆盖算力 / Archs | 最低驱动 / Min driver | 体积 / Size |
| --- | --- | --- | --- | --- |
| 插件根（默认）/ plugin root | CUDA 13.0 | sm_86 / 89 / 120 / 121 | 580.65 | 随包 / bundled |
| `engine-cuda12\` | CUDA 12.4 | sm_50 / 61 / 70 / 75 / 80 / 90 | 525.60 | ≈660 MB |
| `engine-vulkan\` | Vulkan | 任意 / any (arch-independent) | 470 | ≈40 MB |

选型规则 / Selection rule：算力**精确命中**且驱动达标才用 CUDA（13.0 优先于 12.4），
否则落 Vulkan，无 NVIDIA 卡则用 CPU。不做区间外推、不赌 PTX。
CUDA is used only on an **exact arch hit** with a compliant driver (13.0 beats 12.4);
otherwise Vulkan; no NVIDIA GPU → CPU. No range extrapolation, no PTX gambling.

### 3.4 手动切换与回滚 / Manual switch and rollback

```bat
python bsai_engine_select.py --show                   :: 只看探测结果 / probe only
python bsai_engine_select.py --engine auto            :: 恢复自动 / back to auto
python bsai_engine_select.py --engine engine-cuda12   :: 强制 CUDA 12.4
python bsai_engine_select.py --engine engine-vulkan   :: 强制 Vulkan（30 系旧驱动）
```

- `engine-selection.json`：当前选中的引擎（自动生成，可手工改）
- `engine-matrix.json`：各引擎探测出的能力表
- `engine-force.txt`：手工指定（`auto` 或目录名），优先级最高

三个文件都是**本机状态**，已在 `.gitignore` 里排除，不随仓库分发。
All three are per-machine state and are git-ignored.

### 3.5 模型怎么放 / Where to put the weights

节点只推理，权重自备（GGUF）。原生支持 `G:\...\models\LLM` 这种大仓库 + `C:` 侧 Junction，
不需要为每台机器复制一份：

```bat
:: C 盘用一条 Junction 指向 G 盘模型库，两个盘都能读到同一份权重
mklink /J "C:\BSAI\ComfyUI-BSAI_pro_v43\ComfyUI\models\LLM" "G:\BSAI-ComfyUI-intel-XPU-GPU-NPU-aki\ComfyUI\models\LLM"
```

30 系显存与量化档位参考 / VRAM vs quant (30-series)：

| 显存 / VRAM | 典型卡 / Cards | 建议 / Suggested |
| --- | --- | --- |
| 8 GB | 3060 Ti / 3070 / 3070 Ti | Qwen3-8B Q4_K_M（4.68 GB），上下文压到 4k |
| 12 GB | 3060 12G / 3080 12G | Qwen3-8B Q4_K_M 宽裕 / comfortable |
| 24 GB | 3090 / 3090 Ti | 14B Q5_K_M、32B Q4_K_M |

> NVFP4 / `.ninfer` 量化是 Blackwell（sm_120）产物，Ampere 上没有对应算力，30 系请一律用 GGUF。
> NVFP4 / `.ninfer` artifacts target Blackwell (sm_120); Ampere has no matching compute, use GGUF.

---

## 4. 节点 / Node

### BSAI Llama Text Gen (llama.cpp)

本地 GGUF 文本生成，调用**当前选中引擎**的 `llama-cli.exe` 单轮生成。
Local GGUF text generation; calls `llama-cli.exe` from the **currently selected engine**.

| 参数 / Param | 类型 / Type | 说明 / Notes |
| --- | --- | --- |
| `prompt` | STRING | 生成提示词（多行）/ the prompt |
| `model_path` | STRING | 本地 GGUF 绝对路径 / absolute path to a GGUF |
| `n_predict` | INT | 最多生成 token 数，默认 256 / max new tokens |
| `temperature` | FLOAT | 采样温度，默认 0.7 / sampling temperature |
| `n_ctx` | INT | 上下文窗口，默认 2048 / context window |
| `timeout_sec` | INT | 子进程超时秒数，默认 300 / subprocess timeout |
| `extra_args` | STRING（可选） | 附加参数，如 `--top-p 0.9 --repeat-penalty 1.1` |

**输出 / Output**：`text`（STRING）。

---

## 5. 与 BSAI 全家桶协同 / Shared with the BSAI suite

选型结果一份，全家桶共读，不需要各插件分别配 GPU 参数：
One selection file, shared by the whole suite — no per-plugin GPU config:

- `BSAI-llm-Strata` 的 **Flint**（8082）与 **Nemotron**（8085）`llama-server`；
- 模型管理器的 `_find_llama_server()`；
- 本插件节点。

Strata 的 `NInfer` 后端例外：上游只有 `ninfer-sm89` / `ninfer-sm120`，**没有 sm86 构建**，
30 系上会自动跳过并提示改用「llama.cpp (local GGUF)」后端；如果你自建了 `ninfer-sm86`，
放进 `BSAI-FLUX3-ComfyUI\engine\ninfer-sm86\` 即会被选中。
Exception: Strata's NInfer backend has no sm86 build upstream; on 30-series it refuses to run
cross-generation and suggests the llama.cpp GGUF path. Drop your own `ninfer-sm86` into
`BSAI-FLUX3-ComfyUI\engine\ninfer-sm86\` and it gets picked up.

---

## 6. 排障 / Troubleshooting

| 现象 / Symptom | 原因 / Cause | 处理 / Fix |
| --- | --- | --- |
| `no kernel image is available for execution on the device` | 该构建的 cubin 不含你的算力 / arch not in cubin | 升驱动用 CUDA 13，或强制 `--engine engine-vulkan` |
| `--list-devices` 没有 CUDA0 | 缺 `cublas*64_13.dll` / `cudart64_13.dll`，或二进制没解压全 / missing runtime DLLs | 重新解压 725 MB 包到插件根 |
| 选型结果和预期不符 | `engine-force.txt` 里写死了旧值 / stale force file | 改 `auto` 或删除该文件后重跑 `--show` |
| Vulkan 档极慢 / Vulkan is very slow | 多设备时被分到核显 / weights split onto iGPU | `set GGML_VK_VISIBLE_DEVICES=0` 只留独显 |
| 30 系 `engine-cuda12` 起不起来 | 该构建没有 sm_86 cubin（已实测）/ no sm_86 cubin | 这是预期行为，用 CUDA 13 或 Vulkan |

---

## 7. 实测数据 / Benchmarks

测试机 / Test machine：RTX 5090 Laptop（sm_120，驱动 616.56，24 GB），模型
`Qwen3-8B-Q4_K_M`，`llama-bench -ngl 99 -p 64 -n 16`：

| 引擎 / Engine | 后端 / Backend | pp64 (t/s) | tg16 (t/s) |
| --- | --- | --- | --- |
| 插件根 / root | CUDA 13 | 963.46 | 38.43 |
| `engine-vulkan` | Vulkan | 29.54 | 0.73 |
| 插件根（`-ngl 0`）| CPU | 32.01 | 3.84 |

结论 / Takeaways：

- **CUDA 13 是唯一值得用的路径**，30 系升驱动即可获得同量级性能；
- Vulkan 档在 Blackwell 上解码仅 0.73 t/s，**比纯 CPU 还慢**，只是“能加载、能出字”的兜底；
- 30 系真机端到端未实测（测试机无 30 系卡），选型逻辑用伪造 `nvidia-smi` 输出做过十组
  显卡/驱动组合验证（5090 / 4090 / 3090 / 3080 / 3060 / 3070Ti / 2080Ti / 1660 / 1650 / MX450）。
  End-to-end on a real 30-series card was **not** tested (no such card on the test machine);
  the selector was validated against ten simulated arch/driver combinations.

---

## License

MIT（本仓库代码部分 / code in this repo）；llama.cpp 二进制版权归 llama.cpp 项目所有（MIT）。
The bundled llama.cpp binaries remain under the llama.cpp project's MIT license.
