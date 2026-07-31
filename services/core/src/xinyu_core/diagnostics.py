from __future__ import annotations

import ctypes
import os
import platform
import subprocess
from dataclasses import dataclass

from .contracts import GpuCapability, SystemCapabilities


@dataclass(frozen=True, slots=True)
class ProfileRecommendation:
    name: str
    avatar_strategy: str
    notes: list[str]


def recommend_profile(
    gpu_memory_mb: int,
    system_memory_gb: float,
) -> ProfileRecommendation:
    if gpu_memory_mb >= 22_000 and system_memory_gb >= 31:
        return ProfileRecommendation(
            "high_quality_24gb",
            "1080p 状态视频 + 局部实时口型，可提高并发模型常驻预算",
            ["仍使用有界队列和脸部 ROI，不持续生成整帧。"],
        )
    if gpu_memory_mb >= 14_000 and system_memory_gb >= 28:
        return ProfileRecommendation(
            "high_quality_16gb",
            "高质量状态视频 + 局部实时口型，显存紧张时卸载非活跃模型",
            ["优先 720p/25fps 建基准，再验收 1080p/25fps。"],
        )
    if gpu_memory_mb >= 9_000 and system_memory_gb >= 16:
        return ProfileRecommendation(
            "balanced_10gb",
            "高质量预制状态视频 + 按需局部口型",
            ["保持写实资产质量，不回退为 2.5D；必要时降低口型帧率。"],
        )
    return ProfileRecommendation(
        "cpu_compatibility",
        "高质量预制状态视频，实时口型默认关闭",
        ["保留文本和语音链路；不使用低质量 2.5D 作为默认替代。"],
    )


def _memory_gb() -> float:
    if os.name == "nt":
        class MemoryStatus(ctypes.Structure):
            _fields_ = [
                ("length", ctypes.c_ulong),
                ("memory_load", ctypes.c_ulong),
                ("total_physical", ctypes.c_ulonglong),
                ("available_physical", ctypes.c_ulonglong),
                ("total_page_file", ctypes.c_ulonglong),
                ("available_page_file", ctypes.c_ulonglong),
                ("total_virtual", ctypes.c_ulonglong),
                ("available_virtual", ctypes.c_ulonglong),
                ("available_extended_virtual", ctypes.c_ulonglong),
            ]

        status = MemoryStatus()
        status.length = ctypes.sizeof(MemoryStatus)
        if ctypes.windll.kernel32.GlobalMemoryStatusEx(ctypes.byref(status)):
            return round(status.total_physical / 1024**3, 1)
    if hasattr(os, "sysconf"):
        pages = os.sysconf("SC_PHYS_PAGES")
        page_size = os.sysconf("SC_PAGE_SIZE")
        return round(pages * page_size / 1024**3, 1)
    return 0.0


def _nvidia_gpus() -> list[GpuCapability]:
    creation_flags = 0
    if os.name == "nt":
        creation_flags = subprocess.CREATE_NO_WINDOW
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=name,memory.total",
                "--format=csv,noheader,nounits",
            ],
            check=True,
            capture_output=True,
            text=True,
            timeout=4,
            creationflags=creation_flags,
        )
    except (FileNotFoundError, subprocess.SubprocessError):
        return []

    gpus: list[GpuCapability] = []
    for line in result.stdout.splitlines():
        if not line.strip():
            continue
        name, separator, memory = line.rpartition(",")
        if not separator:
            continue
        try:
            gpus.append(
                GpuCapability(
                    name=name.strip(),
                    memory_mb=int(memory.strip()),
                )
            )
        except ValueError:
            continue
    return gpus


def inspect_system() -> SystemCapabilities:
    memory_gb = _memory_gb()
    gpus = _nvidia_gpus()
    gpu_memory_mb = max((gpu.memory_mb for gpu in gpus), default=0)
    recommendation = recommend_profile(gpu_memory_mb, memory_gb)
    return SystemCapabilities(
        platform=f"{platform.system()} {platform.release()}",
        cpu=platform.processor() or platform.machine(),
        logical_cores=os.cpu_count() or 1,
        memory_gb=memory_gb,
        gpus=gpus,
        recommended_profile=recommendation.name,
        avatar_strategy=recommendation.avatar_strategy,
        notes=recommendation.notes,
    )
