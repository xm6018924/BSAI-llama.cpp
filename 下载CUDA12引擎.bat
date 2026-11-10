@echo off
chcp 65001 >nul
setlocal enabledelayedexpansion
title BSAI llama.cpp - 补齐多代显卡引擎（CUDA 12.4 + Vulkan）

rem 补齐两档扩展引擎，让 30 系 / 20 系 / 16 系以及旧驱动机器也能跑本地 llama.cpp：
rem   engine-cuda12\  官方 b12224 CUDA 12.4 构建（sm_50…sm_90，驱动 >= 525.60）
rem   engine-vulkan\ 官方 b12224 Vulkan 构建（与算力无关，30 系旧驱动兜底）
rem 幂等：目标目录已有 llama-server.exe 的档位会跳过。

set "HERE=%~dp0"
set "TMP=%HERE%_dl"
set "TAG=b12224"
set "MIRROR=https://gh-proxy.com/"
set "GH=https://github.com/ggml-org/llama.cpp/releases/download/%TAG%"

if not exist "%TMP%" mkdir "%TMP%"

rem ---------- 1. CUDA 12.4 ----------
if exist "%HERE%engine-cuda12\llama-server.exe" (
    echo [OK] engine-cuda12 已存在，跳过。
) else (
    echo [1/2] 下载 CUDA 12.4 引擎 ^(约 660 MB^) ...
    curl.exe -L --retry 6 --retry-delay 3 --retry-all-errors -o "%TMP%\llama-cuda12.zip" "%MIRROR%%GH%/llama-%TAG%-bin-win-cuda-12.4-x64.zip"
    if errorlevel 1 goto :cuda_fail
    curl.exe -L --retry 6 --retry-delay 3 --retry-all-errors -o "%TMP%\cudart-cuda12.zip" "%MIRROR%%GH%/cudart-llama-bin-win-cuda-12.4-x64.zip"
    if errorlevel 1 goto :cuda_fail
    if not exist "%HERE%engine-cuda12" mkdir "%HERE%engine-cuda12"
    tar -xf "%TMP%\llama-cuda12.zip" -C "%HERE%engine-cuda12"
    if errorlevel 1 goto :unzip_fail
    tar -xf "%TMP%\cudart-cuda12.zip" -C "%HERE%engine-cuda12"
    if errorlevel 1 goto :unzip_fail
    del /q "%TMP%\llama-cuda12.zip" "%TMP%\cudart-cuda12.zip" 2>nul
    echo [OK] engine-cuda12 就位。
)

rem ---------- 2. Vulkan ----------
if exist "%HERE%engine-vulkan\llama-server.exe" (
    echo [OK] engine-vulkan 已存在，跳过。
) else (
    echo [2/2] 下载 Vulkan 引擎 ^(约 40 MB^) ...
    curl.exe -L --retry 6 --retry-delay 3 --retry-all-errors -o "%TMP%\llama-vulkan.zip" "%MIRROR%%GH%/llama-%TAG%-bin-win-vulkan-x64.zip"
    if errorlevel 1 goto :vk_fail
    if not exist "%HERE%engine-vulkan" mkdir "%HERE%engine-vulkan"
    tar -xf "%TMP%\llama-vulkan.zip" -C "%HERE%engine-vulkan"
    if errorlevel 1 goto :unzip_fail
    del /q "%TMP%\llama-vulkan.zip" 2>nul
    echo [OK] engine-vulkan 就位。
)

:probe
echo.
echo 探测当前显卡并选择引擎 ...
set "PY="
for %%P in ("%HERE%..\..\python\python.exe" "%HERE%..\..\..\python\python.exe") do (
    if exist %%~P if not defined PY set "PY=%%~P"
)
if defined PY (
    "%PY%" "%HERE%bsai_engine_select.py" --show
) else (
    echo [提示] 未找到整合包 python，ComfyUI 启动后会自动生成 engine-selection.json。
)
goto :end

:cuda_fail
echo [FAIL] CUDA 12.4 引擎下载失败，请检查网络后重试。
goto :end

:vk_fail
echo [FAIL] Vulkan 引擎下载失败，请检查网络后重试。
goto :end

:unzip_fail
echo [FAIL] 解压失败（需要系统自带 tar，Win10 1803 及以上默认已有）。

:end
echo.
pause
endlocal
