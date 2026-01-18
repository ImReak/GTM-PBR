#!/usr/bin/env python3
from pathlib import Path
from PIL import Image
import argparse


class Zoomer:
    ALLOWED_SCALES = {4, 8}

    def __init__(self, root: Path):
        self.root = Path(root).resolve()

    def _check_scale(self, scale: int) -> None:
        if scale not in self.ALLOWED_SCALES:
            raise ValueError(f"scale需为4或8（当前：{scale}）")

    def scale_image_inplace(self, src: Path, scale: int) -> None:
        self._check_scale(scale)

        with Image.open(src) as im:
            im = im.convert("RGBA")
            new_size = (im.width * scale, im.height * scale)
            out = im.resize(new_size, resample=Image.NEAREST)

        out.save(src, format="PNG")

    def scale_all_pngs_inplace(self, scale: int) -> None:
        self._check_scale(scale)

        for src in self.root.rglob("*.png"):
            try:
                self.scale_image_inplace(src, scale)
                print(f"SUCCESS  {src}")
            except Exception as e:
                print(f"FAIL {src}: {e}")


def main():
    parser = argparse.ArgumentParser(description="递归PNG放大并覆盖原文件：")
    parser.add_argument("root", help="要处理的根目录")
    parser.add_argument("-s", "--scale", type=int, default=8, help="缩放倍率（4 或 8）")
    args = parser.parse_args()

    Zoomer(args.root).scale_all_pngs_inplace(args.scale)


if __name__ == "__main__":
    main()
