from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path
from typing import Optional

import numpy as np
from PIL import Image


@dataclass(frozen=True)
class NormalMapConfig:
    # 基本强度/响应
    strength: float = 4.0          # 凹凸强度（越大越“鼓”）
    edge_gamma: float = 2.0        # 边缘响应的 gamma（越大越抑制弱边缘/噪声）
    edge_norm: float = 0.5         # 色差归一化尺度（越小越敏感）

    # 平滑/去噪
    blur_passes: int = 1           # 对边缘权重做 box blur 次数（0=不模糊）
    edge_threshold: float = 0.20   # 弱边缘阈值（0~1，越大越“只保留大边界”）
    quantize_levels: int = 0       # 颜色量化级别（0=不量化；如 32/64 可降噪）

    # 透明处理 & 方向
    alpha_protect: bool = True     # 透明像素用平面法线
    alpha_threshold: float = 0.01  # 判定透明的阈值
    flip_y: bool = False           # 法线绿通道方向

    # 输出/覆盖策略
    overwrite: bool = True


class NormalMapCreator:
    """
    从颜色贴图 xxx.png 生成法线贴图 xxx_n.png
    相邻像素 RGB 色差 -> 边缘强度；亮度差 -> 边缘方向
    """

    def __init__(self, textures_root: Path):
        self.textures_root = Path(textures_root).resolve()

    @staticmethod
    def _rgb_luma(rgb01: np.ndarray) -> np.ndarray:
        return (0.2126 * rgb01[..., 0] + 0.7152 * rgb01[..., 1] + 0.0722 * rgb01[..., 2]).astype(np.float32)

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
        # levels=64 => step=1/63
        step = 1.0 / (levels - 1)
        return (np.round(rgb01 / step) * step).clip(0.0, 1.0)

    @classmethod
    def _normal_from_color_edges(cls, rgba: np.ndarray, cfg: NormalMapConfig) -> np.ndarray:
        rgb = rgba[..., :3].astype(np.float32) / 255.0
        a = rgba[..., 3].astype(np.float32) / 255.0

        # 可选：颜色量化降低噪点
        if cfg.quantize_levels and cfg.quantize_levels > 1:
            rgb = cls._quantize_rgb(rgb, cfg.quantize_levels)

        # padding
        rgbp = np.pad(rgb, ((1, 1), (1, 1), (0, 0)), mode="edge")

        left  = rgbp[1:-1, 0:-2, :]
        right = rgbp[1:-1, 2:  , :]
        up    = rgbp[0:-2, 1:-1, :]
        down  = rgbp[2:  , 1:-1, :]

        # 1) 边缘强度：相邻色差（无方向）
        dx_mag = np.linalg.norm(right - left, axis=-1)  # 0..sqrt(3)
        dy_mag = np.linalg.norm(down - up, axis=-1)

        # 2) 方向：相邻亮度差（启发式：更亮 = 更高）
        lum_left  = cls._rgb_luma(left)
        lum_right = cls._rgb_luma(right)
        lum_up    = cls._rgb_luma(up)
        lum_down  = cls._rgb_luma(down)

        dx_sign = np.sign(lum_right - lum_left)
        dy_sign = np.sign(lum_down - lum_up)

        # 3) 抑制噪声：色差归一化 + gamma
        #    edge_norm 越大，整体越“平”（不敏感）；越小越容易起颗粒
        dx_w = np.power(np.clip(dx_mag / max(cfg.edge_norm, 1e-6), 0.0, 1.0), cfg.edge_gamma)
        dy_w = np.power(np.clip(dy_mag / max(cfg.edge_norm, 1e-6), 0.0, 1.0), cfg.edge_gamma)

        # 4) 平滑：对权重做 box blur
        for _ in range(max(cfg.blur_passes, 0)):
            dx_w = cls._box_blur_3x3(dx_w)
            dy_w = cls._box_blur_3x3(dy_w)

        # 5) 阈值：弱边缘直接归零，去颗粒
        if cfg.edge_threshold > 0:
            dx_w = np.where(dx_w < cfg.edge_threshold, 0.0, dx_w)
            dy_w = np.where(dy_w < cfg.edge_threshold, 0.0, dy_w)

        gx = dx_sign * dx_w
        gy = dy_sign * dy_w

        nx = -gx * cfg.strength
        ny = (-gy if not cfg.flip_y else +gy) * cfg.strength
        nz = np.ones_like(nx, dtype=np.float32)

        n = np.stack([nx, ny, nz], axis=-1)
        n /= (np.linalg.norm(n, axis=-1, keepdims=True) + 1e-8)

        # 6) 透明保护
        if cfg.alpha_protect:
            mask = (a > cfg.alpha_threshold).astype(np.float32)
            mask3 = np.stack([mask, mask, mask], axis=-1)
            flat = np.array([0.0, 0.0, 1.0], dtype=np.float32)
            n = n * mask3 + flat * (1.0 - mask3)

        out = ((n * 0.5 + 0.5).clip(0, 1) * 255.0 + 0.5).astype(np.uint8)
        return out  # HxWx3 uint8

    def create_for_file(self, png_path: Path, cfg: Optional[NormalMapConfig] = None) -> Optional[Path]:
        cfg = cfg or NormalMapConfig()
        png_path = Path(png_path)

        out_path = png_path.with_name(png_path.stem + "_n.png")
        if (not cfg.overwrite) and out_path.exists():
            return None

        with Image.open(png_path) as im:
            im = im.convert("RGBA")
            rgba = np.array(im, dtype=np.uint8)

        normal = self._normal_from_color_edges(rgba, cfg)
        Image.fromarray(normal, mode="RGB").save(out_path, format="PNG")
        return out_path
