# -*- coding: utf-8 -*-
"""
BSAI-llama.cpp 引擎选择器
=========================

BSAI 全家桶里所有基于 llama.cpp 的引擎（BSAI Llama Text Gen、Flint 8082、
Nemotron 8085、模型管理器）都从本插件目录取 llama-server.exe / llama-cli.exe。
同一份二进制不可能同时满足所有显卡代次，所以本插件按"显卡算力 + 驱动版本"
在多个引擎目录之间选择一个，并把结果写成 engine-selection.json 供其它插件读取。

引擎目录约定（都在本插件目录下）：

    <插件目录>/                     CUDA 13 构建（sm_86 / sm_89 / sm_120）
    <插件目录>/engine-cuda12/       CUDA 12.4 构建（sm_50 … sm_89，驱动门槛更低）

选择规则（按优先级）：

    1. 显卡算力在该引擎的 cubin 列表内，且驱动版本 >= 该引擎的 min_driver；
    2. 多个引擎都满足时，取 CUDA 版本更高的那个（同代卡上新运行时更快）；
    3. 都不满足时，取"算力命中但驱动不够"的那个并把原因写进 selection，
       交给调用方给出可读报错（例如提示升级显卡驱动）。

没有 NVIDIA 显卡（含 nvidia-smi 不可用）时不改动默认选型，直接返回插件根，
让 llama.cpp 自己回退到 CPU / Vulkan。

命令行：
    python bsai_engine_select.py            # 重新探测并写入选择结果
    python bsai_engine_select.py --show     # 只打印当前 probe / 选择，不写文件
    python bsai_engine_select.py --engine engine-cuda12   # 强制指定
    python bsai_engine_select.py --engine auto            # 恢复自动
"""

import json
import os
import re
import subprocess
import time

NODE_DIR = os.path.dirname(os.path.abspath(__file__))
SELECTION_FILE = os.path.join(NODE_DIR, "engine-selection.json")
MATRIX_FILE = os.path.join(NODE_DIR, "engine-matrix.json")
FORCE_FILE = os.path.join(NODE_DIR, "engine-force.txt")

# 缺省能力表：探测失败（例如首次运行还没扫描 dll）时的兜底声明。
# 真实值由 probe_engines() 从各引擎的 ggml-cuda.dll 里读出来写进 engine-matrix.json。
DEFAULT_ENGINES = {
    ".": {
        "label": "CUDA 13 (sm_86/89/120/121)",
        "cuda": 13.0,
        "archs": [86, 89, 120],
        "min_driver": 580.65,
    },
    "engine-cuda12": {
        "label": "CUDA 12.4 (sm_50…90)",
        "cuda": 12.4,
        "archs": [50, 61, 70, 75, 80, 90],
        "min_driver": 525.60,
    },
    # Vulkan 后端与算力无关（驱动自带 Vulkan 运行时即可），是“算力没被任何 CUDA
    # 构建覆盖”或“驱动版本吃不上 CUDA 13”时的通用兜底：30 系旧驱动、MX 系列等。
    "engine-vulkan": {
        "label": "Vulkan (任意算力)",
        "cuda": 0.0,
        "archs": "*",
        "min_driver": 470.00,
    },
}

ARCH_RE = re.compile(r"sm_(\d{2,3})")


# --------------------------------------------------------------------------- GPU
def query_gpu(timeout=8):
    """用 nvidia-smi 读显卡列表：name / compute_cap / driver_version。

    返回 [{"name","cap","arch","driver"}]；任何一步失败返回 []。
    """
    cmd = [
        "nvidia-smi",
        "--query-gpu=name,compute_cap,driver_version",
        "--format=csv,noheader",
    ]
    try:
        out = subprocess.run(
            cmd,
            capture_output=True,
            text=True,
            encoding="utf-8",
            errors="replace",
            timeout=timeout,
        )
    except (OSError, subprocess.SubprocessError):
        return []
    if out.returncode != 0 or not out.stdout.strip():
        return []

    gpus = []
    for line in out.stdout.strip().splitlines():
        parts = [p.strip() for p in line.split(",")]
        if len(parts) < 3:
            continue
        name, cap, driver = parts[0], parts[1], parts[2]
        try:
            arch = int(round(float(cap) * 10))
        except ValueError:
            continue
        try:
            drv = float(driver)
        except ValueError:
            drv = 0.0
        gpus.append({"name": name, "cap": cap, "arch": arch, "driver": drv})
    return gpus


# ----------------------------------------------------------------- 引擎能力探测
def scan_cuda_archs(dll_path):
    """从 ggml-cuda.dll 的二进制里抽 sm_XX cubin 列表。"""
    archs = set()
    try:
        with open(dll_path, "rb") as f:
            data = f.read()
    except OSError:
        return None
    # 只取可打印片段做正则，避免整文件都进 re
    text = data.decode("ascii", errors="ignore")
    for m in ARCH_RE.finditer(text):
        try:
            archs.add(int(m.group(1)))
        except ValueError:
            continue
    return sorted(archs) or None


def probe_engines():
    """扫描每个引擎目录，得出 {rel_dir: {label,cuda,archs,min_driver,exe,...}}。"""
    result = {}
    for rel, meta in DEFAULT_ENGINES.items():
        d = os.path.abspath(os.path.join(NODE_DIR, rel))
        if not os.path.isdir(d):
            continue
        entry = dict(meta)
        entry["dir"] = rel
        entry["exe"] = "llama-server.exe"
        entry["has_server"] = os.path.isfile(os.path.join(d, "llama-server.exe"))
        entry["has_cli"] = os.path.isfile(os.path.join(d, "llama-cli.exe"))
        dll = os.path.join(d, "ggml-cuda.dll")
        archs = scan_cuda_archs(dll) if os.path.isfile(dll) else None
        if archs:
            entry["archs"] = archs
            entry["archs_source"] = "ggml-cuda.dll"
        else:
            entry["archs_source"] = "declared"
        # 各引擎自带的 BUILD.json 更权威（镜像包会带官方构建信息）
        build = os.path.join(d, "BUILD.json")
        if os.path.isfile(build):
            try:
                with open(build, "r", encoding="utf-8") as f:
                    bj = json.load(f)
                if isinstance(bj.get("archs"), list) and bj["archs"]:
                    entry["archs"] = sorted(int(a) for a in bj["archs"])
                    entry["archs_source"] = "BUILD.json"
                if bj.get("cuda"):
                    try:
                        entry["cuda"] = float(bj["cuda"])
                    except (TypeError, ValueError):
                        pass
            except (OSError, ValueError):
                pass
        result[rel] = entry
    return result


def _dir_mtime_sig(engines):
    """引擎目录的轻量指纹，用来判断缓存的 matrix 是否过期。"""
    sig = []
    for rel in sorted(engines):
        d = os.path.abspath(os.path.join(NODE_DIR, rel))
        try:
            sig.append([rel, os.path.getmtime(d)])
        except OSError:
            sig.append([rel, 0])
    return sig


def load_matrix(refresh=False):
    """读取（或重建）engine-matrix.json。"""
    if not refresh and os.path.isfile(MATRIX_FILE):
        try:
            with open(MATRIX_FILE, "r", encoding="utf-8") as f:
                cached = json.load(f)
            if cached.get("sig") == _dir_mtime_sig(cached.get("engines", {}) or DEFAULT_ENGINES):
                return cached.get("engines", {})
        except (OSError, ValueError):
            pass
    engines = probe_engines()
    try:
        with open(MATRIX_FILE, "w", encoding="utf-8") as f:
            json.dump(
                {
                    "sig": _dir_mtime_sig(engines),
                    "engines": engines,
                    "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
                },
                f,
                ensure_ascii=False,
                indent=2,
            )
    except OSError:
        pass
    return engines


# --------------------------------------------------------------------- 选型
def forced_engine():
    """engine-force.txt 里的手工指定（写 engine-cuda12 或 auto）。"""
    try:
        with open(FORCE_FILE, "r", encoding="utf-8") as f:
            v = f.read().strip()
    except OSError:
        return None
    if not v or v.lower() == "auto":
        return None
    return v


def choose(engines, gpus):
    """返回 (selected_rel, reason, gpu_used)。"""
    if not gpus:
        return ".", "未检测到 NVIDIA 显卡（nvidia-smi 不可用），保持默认 llama.cpp 运行时", None

    # 以第一块显卡为准；多卡混插时取算力最低的那块，保证所有卡都能跑
    primary = min(gpus, key=lambda g: g["arch"])
    arch, drv = primary["arch"], primary["driver"]

    fits, arch_only = [], []
    for rel, meta in engines.items():
        if not meta.get("has_server"):
            continue
        archs = meta.get("archs")
        # "*" = 与算力无关的后端（Vulkan）；空表按“已声明的兜底引擎”处理
        wildcard = archs == "*" or not archs
        if wildcard:
            arch_ok = True
        elif isinstance(archs, list):
            # 只认精确命中：官方 CUDA 12.4 构建的 cubin 只到 sm_90，中间代次
            # （sm_86 / sm_89）没有 cubin，靠 PTX 碰运气不如直接走 Vulkan。
            arch_ok = arch in archs
        else:
            arch_ok = True
        if not arch_ok:
            continue
        if drv and drv >= float(meta.get("min_driver") or 0):
            fits.append(rel)
        else:
            arch_only.append(rel)

    def _archs_text(meta):
        a = meta.get("archs")
        if a == "*" or not a:
            return "任意算力"
        return ",".join("sm_%d" % x for x in a)

    if fits:
        best = max(fits, key=lambda r: float(engines[r].get("cuda") or 0))
        meta = engines[best]
        return best, (
            "显卡 %s (sm_%d) 驱动 %s：命中 %s，算力 %s"
            % (primary["name"], arch, primary["driver"], meta.get("label", best),
               _archs_text(meta))
        ), primary

    if arch_only:
        best = max(arch_only, key=lambda r: float(engines[r].get("cuda") or 0))
        meta = engines[best]
        need = meta.get("min_driver")
        return best, (
            "显卡 %s (sm_%d) 驱动 %s 低于最低要求 %s，请在显卡驱动升级后重启；"
            "已按算力选择 %s 尽力运行" % (primary["name"], arch, primary["driver"],
                                        need, meta.get("label", best))
        ), primary

    return ".", (
        "显卡 %s (sm_%d) 不在任何已部署引擎的 cubin 列表内，保持默认运行时（可能回退 CPU）"
        % (primary["name"], arch)
    ), primary


def engine_path(rel):
    if rel in (".", "", None):
        return NODE_DIR
    return os.path.join(NODE_DIR, rel)


def resolve_engine_dir(force=False):
    """给插件内部用：返回当前应使用的引擎绝对目录。"""
    engines = load_matrix(refresh=False)
    forced = forced_engine()
    if forced and forced in engines:
        return engine_path(forced)
    if not force and os.path.isfile(SELECTION_FILE):
        try:
            with open(SELECTION_FILE, "r", encoding="utf-8") as f:
                sel = json.load(f)
            rel = sel.get("selected")
            if rel in engines and engines[rel].get("has_server"):
                return engine_path(rel)
        except (OSError, ValueError):
            pass
    rel, reason, gpu = choose(engines, query_gpu())
    write_selection(rel, reason, gpu, engines)
    return engine_path(rel)


def write_selection(rel, reason, gpu, engines):
    meta = engines.get(rel, {})
    payload = {
        "selected": rel,
        "label": meta.get("label", ""),
        "engine_dir": engine_path(rel),
        "llama_server": os.path.join(engine_path(rel), "llama-server.exe"),
        "llama_cli": os.path.join(engine_path(rel), "llama-cli.exe"),
        "cuda": meta.get("cuda"),
        "archs": meta.get("archs"),
        "min_driver": meta.get("min_driver"),
        "reason": reason,
        "gpu": gpu,
        "updated": time.strftime("%Y-%m-%d %H:%M:%S"),
    }
    try:
        with open(SELECTION_FILE, "w", encoding="utf-8") as f:
            json.dump(payload, f, ensure_ascii=False, indent=2)
    except OSError:
        pass
    return payload


# --------------------------------------------------------------------- CLI
def main(argv=None):
    import sys

    argv = list(sys.argv[1:] if argv is None else argv)
    if "--show" in argv:
        engines = load_matrix(refresh=True)
        gpus = query_gpu()
        rel, reason, gpu = choose(engines, gpus)
        print(json.dumps(
            {"gpu": gpus, "engines": engines, "selected": rel, "reason": reason},
            ensure_ascii=False, indent=2))
        return 0
    if "--engine" in argv:
        i = argv.index("--engine")
        val = argv[i + 1] if i + 1 < len(argv) else "auto"
        try:
            with open(FORCE_FILE, "w", encoding="utf-8") as f:
                f.write(val)
        except OSError as exc:
            print("写入 engine-force.txt 失败: %s" % exc)
            return 1
        print("已设置强制引擎: %s" % val)
        if os.path.isfile(SELECTION_FILE):
            try:
                os.remove(SELECTION_FILE)
            except OSError:
                pass
    engines = load_matrix(refresh=True)
    forced = forced_engine()
    if forced and forced in engines:
        rel, reason = forced, "engine-force.txt 手工指定 %s" % forced
        payload = write_selection(rel, reason, query_gpu(), engines)
    else:
        rel, reason, gpu = choose(engines, query_gpu())
        payload = write_selection(rel, reason, gpu, engines)
    print(json.dumps(payload, ensure_ascii=False, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
