from pathlib import Path
from PicZoomer import Zoomer

import tkinter as tk
from tkinter import filedialog, messagebox


class TexturesPreProcessor:
    def __init__(self, assets_root: Path):
        self.assets_root = Path(assets_root).resolve()
        self.folder_scales = {
            "item": 4,
            "models": 4,
            "entity": 4,
            "armor": 4,
            "block": 8,
        }

    def run(self) -> dict:
        textures_root = self.assets_root / "gtceu" / "textures"
        if not textures_root.exists():
            raise FileNotFoundError(f"找不到目录：{textures_root}")

        summary = {}

        for folder_name, scale in self.folder_scales.items():
            folder_path = textures_root / folder_name

            if not folder_path.exists():
                summary[folder_name] = {"scale": scale, "ok": 0, "err": 0, "skip": 0, "missing": True}
                print(f"[WARN] {folder_name}: missing, skipped")
                continue

            zoomer = Zoomer(folder_path)
            png_list = sorted(folder_path.rglob("*.png"))

            ok_count = err_count = skip_count = 0
            total = len(png_list)

            print(f"[INFO] {folder_name}: found {total} png(s), scale x{scale}")

            for i, png in enumerate(png_list, start=1):
                stem = png.stem.lower()
                if stem.endswith("_n") or stem.endswith("_s"):
                    skip_count += 1
                    continue

                try:
                    zoomer.scale_image_inplace(png, scale=scale)
                    ok_count += 1
                except Exception as e:
                    err_count += 1
                    print(f"[ERROR] {folder_name} {png}: {e}")

                if i % 100 == 0 or i == total:
                    print(f"[MONITOR] {folder_name}: {i}/{total} done (ok={ok_count}, err={err_count}, skip={skip_count})")

            print(f"[DONE] {folder_name}: ok={ok_count}, err={err_count}, skip={skip_count}")

            summary[folder_name] = {
                "scale": scale,
                "ok": ok_count,
                "err": err_count,
                "skip": skip_count,
                "missing": False,
            }

        return summary


def format_summary(summary: dict) -> str:
    lines = []
    total_ok = total_err = total_skip = 0

    for folder_name, info in summary.items():
        scale = info["scale"]
        if info.get("missing"):
            lines.append(f"{folder_name}: （目录不存在，跳过）目标倍率 x{scale}")
            continue

        okc, errc, skc = info["ok"], info["err"], info["skip"]
        total_ok += okc
        total_err += errc
        total_skip += skc
        lines.append(f"{folder_name}: x{scale}  成功 {okc}  失败 {errc}  跳过 {skc}")

    lines.append("")
    lines.append(f"总计：成功 {total_ok}  失败 {total_err}  跳过 {total_skip}")
    return "\n".join(lines)


def main():
    root = tk.Tk()
    root.withdraw()

    try:
        folder = filedialog.askdirectory(title="请选择 assets 根目录")
        if not folder:
            messagebox.showinfo("取消", "未选择目录，程序退出。")
            return

        assets_root = Path(folder)
        summary = TexturesPreProcessor(assets_root).run()
        messagebox.showinfo("完成", format_summary(summary))

    except Exception as e:
        messagebox.showerror("错误", str(e))

    finally:
        root.destroy()


if __name__ == "__main__":
    main()
