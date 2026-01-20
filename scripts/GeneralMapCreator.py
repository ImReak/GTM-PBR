from __future__ import annotations

from pathlib import Path
import tkinter as tk
from tkinter import filedialog, messagebox
from collections import defaultdict

from NormalMapCreator import NormalMapCreator, NormalMapConfig
from MetalnessMapCreator import MetalnessMapCreator, MetalnessMapConfig


# Presets
NORMAL_PRESETS = {
    "potato_normal": NormalMapConfig(
        strength=2.0,
        edge_gamma=4.2,
        edge_threshold=0.42,
        blur_passes=3,
        quantize_levels=128,
        alpha_protect=True,
        flip_y=False,
        overwrite=True,
    ),
    "low_normal": NormalMapConfig(
        strength=2.8,
        edge_gamma=3.2,
        edge_threshold=0.32,
        blur_passes=2,
        quantize_levels=64,
        alpha_protect=True,
        flip_y=False,
        overwrite=True,
    ),
    "medium_normal": NormalMapConfig(
        strength=3.6,
        edge_gamma=2.6,
        edge_threshold=0.26,
        blur_passes=1,
        quantize_levels=32,
        alpha_protect=True,
        flip_y=False,
        overwrite=True,
    ),
    "high_normal": NormalMapConfig(
        strength=4.4,
        edge_gamma=2.0,
        edge_threshold=0.18,
        blur_passes=0,
        quantize_levels=16,
        alpha_protect=True,
        flip_y=False,
        overwrite=True,
    ),
    "extreme_normal": NormalMapConfig(
        strength=5.8,
        edge_gamma=1.7,
        edge_threshold=0.14,
        blur_passes=0,
        quantize_levels=12,
        alpha_protect=True,
        flip_y=False,
        overwrite=True,
    ),
    "ultra_normal": NormalMapConfig(
        strength=5.2,
        edge_gamma=1.4,
        edge_threshold=0.10,
        blur_passes=0,
        quantize_levels=8,
        alpha_protect=True,
        flip_y=False,
        overwrite=True,
    ),
}

METALNESS_PRESETS = {
    "high_reflect": MetalnessMapConfig(
        val_bias=0.18,
        gain=1.8,
        gamma=1.05,
        threshold=0.10,
        blur_passes=1,
        quantize_levels=64,
        alpha_affects=True,
        overwrite=True,
    ),
    "medium_reflect": MetalnessMapConfig(
        val_bias=0.28,
        gain=1.5,
        gamma=1.15,
        threshold=0.16,
        blur_passes=1,
        quantize_levels=64,
        alpha_affects=True,
        overwrite=True,
    ),
    "low_reflect": MetalnessMapConfig(
        val_bias=0.45,
        gain=1.1,
        gamma=1.35,
        threshold=0.30,
        blur_passes=0,
        quantize_levels=64,
        alpha_affects=True,
        overwrite=True,
    ),
}

DEFAULT_NORMAL_PRESET = "medium_normal"
DEFAULT_METALNESS_PRESET = "medium_reflect"


PATH_RULES = [
    ("block/casings/coils/", "ultra_normal", "low_reflect"),
    ("block/casings/battery/", "high_normal", "medium_reflect"),
    ("block/casings/", "extreme_normal", "low_reflect"),
    ("block/machines/", "high_normal", "medium_reflect"),
    ("block/overlay/", "high_normal", "medium_reflect"),
    ("block/lamps/", "extreme_normal", "medium_reflect"),
    ("block/", "high_normal", "medium_reflect"),
    ("item/", "low_normal",  "medium_reflect"),
    ("entity/", "medium_normal",  "low_reflect"),
    ("armor/",  "medium_normal",  "low_reflect"),
    ("models/", "medium_normal",  "low_reflect"),
]

NAME_RULES = [
    ("circuit_board", "low_normal", "medium_reflect"),
    ("boule", "low_normal", "medium_reflect"),
    ("wafer", "low_normal", "medium_reflect"),
    ("integrated_circuit", "potato_normal", "medium_reflect"),
    ("microchip_processor", "potato_normal", "medium_reflect"),
    ("micro_processor", "potato_normal", "medium_reflect"),
    ("nano_processor", "potato_normal", "medium_reflect"),
    ("quantum_processor", "potato_normal", "medium_reflect"),
    ("crystal_processor", "potato_normal", "medium_reflect"),
    ("wetware_processor", "potato_normal", "medium_reflect"),
]


EXCLUDE_PATH_PREFIXES = [
]


class GeneralMapCreator:
    def __init__(self, assets_root: Path):
        self.assets_root = Path(assets_root).resolve()

    def _textures_root(self) -> Path:
        return self.assets_root / "gtceu" / "textures"

    @staticmethod
    def _to_rel_posix(textures_root: Path, p: Path) -> str:
        return p.relative_to(textures_root).as_posix()

    @staticmethod
    def _top_group(rel_posix: str) -> str:
        parts = rel_posix.split("/")
        return parts[0] if len(parts) > 1 else "(root)"

    def _pick_presets(self, rel_posix: str, stem_lower: str) -> tuple[str, str, str]:
        # 0) exclude
        for ex in EXCLUDE_PATH_PREFIXES:
            if rel_posix.startswith(ex):
                return (DEFAULT_NORMAL_PRESET, DEFAULT_METALNESS_PRESET, f"exclude:{ex}")

        # 1) name rules
        for sub, n_key, m_key in NAME_RULES:
            if sub in stem_lower:
                return (n_key, m_key, f"name:{sub}")

        # 2) path rules
        for prefix, n_key, m_key in PATH_RULES:
            if rel_posix.startswith(prefix):
                return (n_key, m_key, f"path:{prefix}")

        return (DEFAULT_NORMAL_PRESET, DEFAULT_METALNESS_PRESET, "default")

    def run(self, progress_every: int = 200, debug_rule: bool = False) -> dict:
        textures_root = self._textures_root()
        if not textures_root.exists():
            raise FileNotFoundError(f"找不到目录：{textures_root}")

        normal_creator = NormalMapCreator(textures_root)
        metal_creator = MetalnessMapCreator(textures_root)

        png_list = sorted(textures_root.rglob("*.png"))

        total_scanned = len(png_list)
        total_skipped_ns = 0
        total_excluded = 0
        total_source = 0

        n_ok = n_err = n_skip = 0
        s_ok = s_err = s_skip = 0

        per_group = defaultdict(lambda: {
            "source": 0, "excluded": 0, "skip_ns": 0,
            "n_ok": 0, "n_err": 0, "n_skip": 0,
            "s_ok": 0, "s_err": 0, "s_skip": 0,
        })

        preset_hits = defaultdict(int)

        errors = []

        for idx, png in enumerate(png_list, start=1):
            rel_posix = self._to_rel_posix(textures_root, png)
            group = self._top_group(rel_posix)
            stem_lower = png.stem.lower()

            if stem_lower.endswith("_n") or stem_lower.endswith("_s"):
                total_skipped_ns += 1
                per_group[group]["skip_ns"] += 1
                continue

            n_key, m_key, matched_by = self._pick_presets(rel_posix, stem_lower)

            if matched_by.startswith("exclude:"):
                total_excluded += 1
                per_group[group]["excluded"] += 1
                continue

            total_source += 1
            per_group[group]["source"] += 1

            preset_hits[f"n:{n_key}"] += 1
            preset_hits[f"s:{m_key}"] += 1
            preset_hits[f"rule:{matched_by}"] += 1

            if debug_rule and idx % progress_every == 0:
                print(f"[RULE] {rel_posix} -> n={n_key}, s={m_key}, by={matched_by}")

            # Normal
            try:
                out_n = normal_creator.create_for_file(png, NORMAL_PRESETS[n_key])
                if out_n is None:
                    n_skip += 1
                    per_group[group]["n_skip"] += 1
                else:
                    n_ok += 1
                    per_group[group]["n_ok"] += 1
            except Exception as e:
                n_err += 1
                per_group[group]["n_err"] += 1
                errors.append(f"[N] {rel_posix} -> {type(e).__name__}: {e}")

            # Metalness
            try:
                out_s = metal_creator.create_for_file(png, METALNESS_PRESETS[m_key])
                if out_s is None:
                    s_skip += 1
                    per_group[group]["s_skip"] += 1
                else:
                    s_ok += 1
                    per_group[group]["s_ok"] += 1
            except Exception as e:
                s_err += 1
                per_group[group]["s_err"] += 1
                errors.append(f"[S] {rel_posix} -> {type(e).__name__}: {e}")

            if idx % progress_every == 0 or idx == total_scanned:
                print(f"[PROG] {idx}/{total_scanned} scanned | source={total_source} | n(ok={n_ok},err={n_err},skip={n_skip}) | s(ok={s_ok},err={s_err},skip={s_skip})")

        report_path = Path(__file__).resolve().parent / "error_report.txt"
        if errors:
            report_path.write_text("\n".join(errors), encoding="utf-8")
        else:
            try:
                if report_path.exists():
                    report_path.unlink()
            except Exception:
                pass

        return {
            "textures_root": str(textures_root),
            "total_scanned": total_scanned,
            "total_skipped_ns": total_skipped_ns,
            "total_excluded": total_excluded,
            "total_source": total_source,
            "normal": {"ok": n_ok, "err": n_err, "skip": n_skip},
            "metal": {"ok": s_ok, "err": s_err, "skip": s_skip},
            "per_group": dict(per_group),
            "preset_hits": dict(preset_hits),
            "error_report": str(report_path) if errors else "",
            "error_count": len(errors),
        }


def _format_summary(result: dict) -> str:
    lines = []
    lines.append(f"textures: {result['textures_root']}")
    lines.append("")
    lines.append(f"scanned .png: {result['total_scanned']}")
    lines.append(f"skipped (_n/_s): {result['total_skipped_ns']}")
    lines.append(f"excluded (rules): {result['total_excluded']}")
    lines.append(f"source images: {result['total_source']}")
    lines.append("")
    lines.append(f"_n: ok={result['normal']['ok']}  err={result['normal']['err']}  skip={result['normal']['skip']}")
    lines.append(f"_s: ok={result['metal']['ok']}  err={result['metal']['err']}  skip={result['metal']['skip']}")

    if result["error_count"] > 0:
        lines.append("")
        lines.append(f"errors: {result['error_count']}  (see error_report.txt)")
    lines.append("")

    lines.append("per folder (top-level):")
    per_group = result["per_group"]
    for g in sorted(per_group.keys()):
        s = per_group[g]
        lines.append(
            f"- {g}: source={s['source']} excluded={s['excluded']} skip_ns={s['skip_ns']} | "
            f"n(ok={s['n_ok']},err={s['n_err']},skip={s['n_skip']}) | "
            f"s(ok={s['s_ok']},err={s['s_err']},skip={s['s_skip']})"
        )

    hits = result["preset_hits"]
    if hits:
        lines.append("")
        lines.append("preset hits (top 12):")
        top = sorted(hits.items(), key=lambda kv: kv[1], reverse=True)[:12]
        for k, v in top:
            lines.append(f"- {k}: {v}")

    return "\n".join(lines)


def main():
    root = tk.Tk()
    root.withdraw()

    try:
        folder = filedialog.askdirectory(title="请选择 assets 根目录")
        if not folder:
            messagebox.showinfo("取消", "未选择目录，程序退出。")
            return

        result = GeneralMapCreator(Path(folder)).run(progress_every=200, debug_rule=False)
        messagebox.showinfo("完成", _format_summary(result))

    except Exception as e:
        messagebox.showerror("错误", str(e))

    finally:
        root.destroy()


if __name__ == "__main__":
    main()
