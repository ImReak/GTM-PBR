from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class MetalnessMapConfig:
    # 基本模型
    val_bias: float = 0.2
    gain: float = 1.8

    # 亮度与低饱和的权重
    val_power: float = 1.0         # >1 更偏向高亮区域
    inv_sat_power: float = 1.0     # >1 更偏向低饱和区域
    mix: float = 1.0               # 0~1，0=几乎不看饱和/亮度

    # 阈值与曲线
    threshold: float = 0.0         # 0~1，输出前阈值（小于该值 -> 0）
    gamma: float = 1.0             # 对 metal 结果做 gamma（<1 更亮，>1 更暗）

    # 去噪
    blur_passes: int = 0           # 0=不模糊；1/2 可轻微平滑
    quantize_levels: int = 0       # 0=不量化；如 64/32 可减少噪点影响

    # alpha 处理
    alpha_affects: bool = True
    alpha_threshold: float = 0.01  # alpha<=阈值处强制 metal=0

    # 输出策略
    overwrite: bool = True


class MetalnessMapCreator:
    """
    从颜色贴图 xxx.png 生成金属度贴图 xxx_s.png
    亮且低饱和 -> 更金属
    """

    def __init__(self, textures_root: Path):
        self.textures_root = Path(textures_root).resolve()

    @staticmethod
    def _box_blur_3x3(m: np.ndarray) -> np.ndarray:
        p = np.pad(m, ((1, 1), (1, 1)), mode="edge")
        return (
            p[0:-2, 0:-2] + p[0:-2, 1:-1] + p[0:-2, 2:  ] +
            p[1:-1, 0:-2] + p[1:-1, 1:-1] + p[1:-1, 2:  ] +
            p[2:  , 0:-2] + p[2:  , 1:-1] + p[2:  , 2:  ]
        ) / 9.0

    @staticmethod
    def _quantize_rgb(rgb01: np.ndarray, levels: int) -> np.ndarray:
        if levels <= 1:
            return rgb01
        step = 1.0 / (levels - 1)
        return (np.round(rgb01 / step) * step).clip(0.0, 1.0)

    @classmethod
    def _metalness_from_albedo(cls, rgba: np.ndarray, cfg: MetalnessMapConfig) -> np.ndarray:
        rgb = rgba[..., :3].astype(np.float32) / 255.0
        a = rgba[..., 3].astype(np.float32) / 255.0

        if cfg.quantize_levels and cfg.quantize_levels > 1:
            rgb = cls._quantize_rgb(rgb, cfg.quantize_levels)

        r, g, b = rgb[..., 0], rgb[..., 1], rgb[..., 2]
        cmax = np.maximum(np.maximum(r, g), b)
        cmin = np.minimum(np.minimum(r, g), b)
        delta = cmax - cmin

        sat = np.where(cmax > 1e-6, delta / (cmax + 1e-6), 0.0)
        val = cmax

        val_term = np.power(np.clip(val - cfg.val_bias, 0.0, 1.0), cfg.val_power)
        inv_sat_term = np.power(np.clip(1.0 - sat, 0.0, 1.0), cfg.inv_sat_power)

        metal = val_term * inv_sat_term
        metal = (metal * cfg.gain).clip(0.0, 1.0)

        # 结果曲线
        if cfg.gamma != 1.0:
            # gamma>1 变暗，gamma<1 变亮
            metal = np.power(np.clip(metal, 0.0, 1.0), cfg.gamma)

        # 阈值：让结果更“块状”、减少零碎斑点
        if cfg.threshold > 0.0:
            metal = np.where(metal < cfg.threshold, 0.0, metal)

        # 去噪：轻模糊
        for _ in range(max(cfg.blur_passes, 0)):
            metal = cls._box_blur_3x3(metal.astype(np.float32)).astype(np.float32)
            metal = np.clip(metal, 0.0, 1.0)

        # alpha 影响
        if cfg.alpha_affects:
            metal = metal * a
            metal = np.where(a <= cfg.alpha_threshold, 0.0, metal)

        return (metal * 255.0 + 0.5).astype(np.uint8)

    def create_for_file(self, png_path: Path, cfg: Optional[MetalnessMapConfig] = None) -> Optional[Path]:
        cfg = cfg or MetalnessMapConfig()
        png_path = Path(png_path)
        out_path = png_path.with_name(png_path.stem + "_s.png")

        if (not cfg.overwrite) and out_path.exists():
            return None

        with Image.open(png_path) as im:
            im = im.convert("RGBA")
            rgba = np.array(im, dtype=np.uint8)

        metal = self._metalness_from_albedo(rgba, cfg)
        Image.fromarray(metal, mode="L").save(out_path, format="PNG")
        return out_path
