# -*- coding: utf-8 -*-
"""
BSAI-llama.cpp — ComfyUI 最小 llama.cpp 推理节点
v1.0.0 (2026-10-28)

在插件目录内调用 llama-cli.exe（llama.cpp 预编译二进制，经夸克网盘分发），
对本地 GGUF 模型做单轮文本生成。节点无 comfy 硬依赖，纯标准库实现。
"""
import os
import shutil
import subprocess
import sys

NODE_DIR = os.path.dirname(os.path.abspath(__file__))

if NODE_DIR not in sys.path:
    sys.path.insert(0, NODE_DIR)

# 多代显卡支持：插件根是 CUDA 13 构建（sm_86/89/120），engine-cuda12/ 是
# CUDA 12.4 构建（sm_50…89，驱动门槛更低，覆盖 30 系/20 系/16 系老驱动）。
# 具体用哪一个由 bsai_engine_select 按“显卡算力 + 驱动版本”决定。
ENGINE_DIR = NODE_DIR


def resolve_engine_dir():
    """当前应使用的 llama.cpp 引擎目录（绝对路径）。"""
    global ENGINE_DIR
    try:
        import bsai_engine_select as _sel
        ENGINE_DIR = _sel.resolve_engine_dir()
    except Exception as exc:  # 选择器出问题时不影响节点可用性
        print(f"[BSAI-llama] 引擎选择器不可用，回退插件根目录: {exc}")
        ENGINE_DIR = NODE_DIR
    return ENGINE_DIR


def resolve_llama_cli():
    """优先使用选定引擎目录内的 llama-cli.exe，其次插件根，最后回退到 PATH。"""
    cli_name = "llama-cli.exe"
    for d in (resolve_engine_dir(), NODE_DIR):
        local = os.path.join(d, cli_name)
        if os.path.isfile(local):
            return local
    for name in ("llama-cli", "llama-cli.exe"):
        found = shutil.which(name)
        if found:
            return found
    return local


class BSAILlamaTextGen:
    """BSAI Llama Text Gen — 调用 llama.cpp llama-cli 对本地 GGUF 模型做文本生成。

    输入:
      prompt        生成提示词（多行）
      model_path    本地 GGUF 模型绝对路径（用户自备，如 qwen3 / deepseek 系列 GGUF）
      n_predict     最多生成的 token 数
      temperature   采样温度
      n_ctx         上下文窗口长度
      timeout_sec   子进程超时（秒）
      extra_args    附加 llama-cli 参数（空格分隔，如 --top-p 0.9 --repeat-penalty 1.1）
    输出:
      text          模型生成的文本
    """

    @classmethod
    def INPUT_TYPES(cls):
        return {
            "required": {
                "prompt": ("STRING", {"multiline": True, "default": ""}),
                "model_path": (
                    "STRING",
                    {"default": "", "placeholder": "G:\\models\\llama\\qwen3.gguf"},
                ),
                "n_predict": ("INT", {"default": 256, "min": 1, "max": 32768}),
                "temperature": ("FLOAT", {"default": 0.7, "min": 0.0, "max": 2.0, "step": 0.05}),
                "n_ctx": ("INT", {"default": 2048, "min": 256, "max": 131072}),
                "timeout_sec": ("INT", {"default": 300, "min": 10, "max": 3600}),
            },
            "optional": {
                "extra_args": (
                    "STRING",
                    {"default": "", "placeholder": "--top-p 0.9 --repeat-penalty 1.1"},
                ),
            },
        }

    RETURN_TYPES = ("STRING",)
    RETURN_NAMES = ("text",)
    FUNCTION = "generate"
    CATEGORY = "BSAI/llama.cpp"

    def generate(self, prompt, model_path, n_predict, temperature, n_ctx, timeout_sec, extra_args=""):
        cli = resolve_llama_cli()
        if not os.path.isfile(cli):
            raise RuntimeError(
                f"[BSAI-llama] 未找到 llama-cli.exe: {cli}\n"
                "请先从夸克网盘下载 BSAI-llama.cpp 二进制包并解压到本插件目录"
                "（详见 README.md）。"
            )
        if not model_path or not os.path.isfile(model_path):
            raise RuntimeError(f"[BSAI-llama] GGUF 模型未找到: {model_path or '(空)'}")

        cmd = [
            cli, "-m", model_path, "-p", prompt,
            "-n", str(n_predict), "--temp", str(temperature),
            "-c", str(n_ctx), "--no-display-prompt", "--no-conversation",
        ]
        if extra_args and str(extra_args).strip():
            cmd += str(extra_args).split()

        try:
            proc = subprocess.run(
                cmd,
                capture_output=True,
                text=True,
                encoding="utf-8",
                errors="replace",
                timeout=timeout_sec,
                creationflags=0,
            )
        except subprocess.TimeoutExpired:
            raise RuntimeError(f"[BSAI-llama] llama-cli 执行超时（{timeout_sec}s），可调大 timeout_sec 或缩短 prompt/n_predict。")
        except OSError as exc:
            raise RuntimeError(f"[BSAI-llama] 启动 llama-cli 失败: {exc}")

        if proc.returncode != 0:
            tail = (proc.stderr or "")[-2000:].strip()
            raise RuntimeError(
                f"[BSAI-llama] llama-cli 退出码 {proc.returncode}：{tail or '(无错误输出)'}"
            )

        out = (proc.stdout or "").strip()
        return (out,)


NODE_CLASS_MAPPINGS = {
    "BSAILlamaTextGen": BSAILlamaTextGen,
}

NODE_DISPLAY_NAME_MAPPINGS = {
    "BSAILlamaTextGen": "BSAI Llama Text Gen (llama.cpp)",
}

__all__ = ["NODE_CLASS_MAPPINGS", "NODE_DISPLAY_NAME_MAPPINGS"]
