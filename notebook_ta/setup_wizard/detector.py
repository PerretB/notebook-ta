"""Hardware detection and model auto-selection for the setup wizard."""

from __future__ import annotations

import platform
import subprocess
from dataclasses import dataclass

from notebook_ta.config.models import ModelSpec


@dataclass
class HardwareProfile:
    """Detected hardware resources."""

    ram_gb: float
    vram_gb: float = 0.0
    gpu_name: str | None = None


def _detect_ram() -> float:
    """Return total system RAM in GB. Returns 0.0 on failure."""
    try:
        import psutil  # type: ignore[import-untyped]

        return float(psutil.virtual_memory().total / 1e9)
    except Exception:
        return 0.0


def _detect_nvidia_gpu() -> tuple[float, str | None]:
    """Return (vram_gb, gpu_name) from nvidia-smi. Returns (0.0, None) on failure."""
    try:
        result = subprocess.run(
            [
                "nvidia-smi",
                "--query-gpu=memory.total,name",
                "--format=csv,noheader,nounits",
            ],
            capture_output=True,
            text=True,
            timeout=5,
        )
        if result.returncode != 0:
            return 0.0, None
        line = result.stdout.strip().splitlines()[0]
        parts = line.split(",", 1)
        vram_mb = float(parts[0].strip())
        gpu_name = parts[1].strip() if len(parts) > 1 else None
        return vram_mb / 1024.0, gpu_name
    except Exception:
        return 0.0, None


def _detect_apple_silicon(ram_gb: float) -> tuple[float, str | None]:
    """Estimate unified VRAM for Apple Silicon. Returns (vram_gb, gpu_name) or (0.0, None)."""
    try:
        processor = platform.processor()
        machine = platform.machine()
        if "arm" in processor.lower() or "arm" in machine.lower():
            # Apple Silicon: unified memory shared between CPU and GPU
            return ram_gb, "Apple Silicon (unified memory)"
    except Exception:
        pass
    return 0.0, None


def detect_hardware() -> HardwareProfile:
    """Detect available RAM and GPU resources.

    Each detection step is non-fatal; failures default to 0 / None.

    Returns:
        A HardwareProfile with detected resources.
    """
    ram_gb = _detect_ram()

    # Try NVIDIA first
    vram_gb, gpu_name = _detect_nvidia_gpu()

    # Fall back to Apple Silicon detection
    if vram_gb == 0.0:
        vram_gb, gpu_name = _detect_apple_silicon(ram_gb)

    return HardwareProfile(ram_gb=ram_gb, vram_gb=vram_gb, gpu_name=gpu_name)


def select_model(
    available_models: list[ModelSpec],
    profile: HardwareProfile,
) -> ModelSpec | None:
    """Select the best-fitting model for the detected hardware.

    Returns the ModelSpec with the highest ``min_ram_gb`` whose requirements
    are met (``profile.ram_gb >= spec.min_ram_gb`` and
    ``profile.vram_gb >= spec.min_vram_gb``).

    Args:
        available_models: Candidate ModelSpec entries from the configuration.
        profile: Detected hardware profile.

    Returns:
        The best-fitting ModelSpec, or None if no model fits.
    """
    candidates = [
        spec
        for spec in available_models
        if profile.ram_gb >= spec.min_ram_gb and profile.vram_gb >= spec.min_vram_gb
    ]
    if not candidates:
        return None
    return max(candidates, key=lambda s: s.min_ram_gb)
