from __future__ import annotations

import json
import shutil
from pathlib import Path


def segmentation_result_dir(data_dir: Path) -> Path:
    """切片 TIFF、pkl、等与分割相关的输出根目录：``{data_dir}/segmentation_result``"""
    return (data_dir / "segmentation_result").resolve()


def marked_result_dir(data_dir: Path) -> Path:
    """单木位置可视化：``{data_dir}/segmentation_result/marked_result``"""
    return (segmentation_result_dir(data_dir) / "marked_result").resolve()


def dom_tile_paths(data_dir: Path, stem: str) -> list[Path]:
    """某 DOM stem 对应的全部切片路径（与 pkl 同在 segmentation_result）。"""
    return sorted(segmentation_result_dir(data_dir).glob(f"{stem}_tile_r*_c*.tif"))


def read_upload_manifest(
    user_dir: Path, manifest_name: str = ".upload_manifest.json"
) -> dict[str, str]:
    p = user_dir / manifest_name
    if not p.is_file():
        return {}
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except Exception:
        return {}
    out: dict[str, str] = {}
    for k in ("dom", "chm", "csv"):
        v = raw.get(k)
        if isinstance(v, str) and v.strip():
            out[k] = v.strip()
    return out


def write_upload_manifest(
    user_dir: Path,
    manifest: dict[str, str],
    manifest_name: str = ".upload_manifest.json",
) -> None:
    (user_dir / manifest_name).write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2),
        encoding="utf-8",
    )


def safe_unlink_user_file(path: Path) -> None:
    try:
        if path.is_file():
            path.unlink()
    except OSError:
        pass


def remove_legacy_tile_result_dir(data_dir: Path) -> None:
    """历史 ``tile_result`` 与 segmentation_result 并存时仅保留后者；上传替换时可删遗留目录。"""
    tr = (data_dir / "tile_result").resolve()
    if tr.is_dir():
        shutil.rmtree(tr, ignore_errors=True)


def wipe_segmentation_result(data_dir: Path) -> None:
    seg = segmentation_result_dir(data_dir)
    if seg.is_dir():
        shutil.rmtree(seg, ignore_errors=True)


def unlink_if_exists(path: Path) -> None:
    if path.is_file():
        path.unlink()


def remove_prior_vis_outputs(marked_dir: Path, tile_stem: str, pkl_stem: str) -> None:
    """删除旧版固定命名 ``{tile}_vis.png`` 及 centers 遗留（与按参数后缀命名共存清理）。"""
    vis_path = marked_dir / f"{tile_stem}_vis.png"
    legacy_centers = marked_dir / f"{pkl_stem}_centers.png"
    for p in (
        vis_path,
        vis_path.with_suffix(".json"),
        legacy_centers,
        legacy_centers.with_suffix(".json"),
    ):
        unlink_if_exists(p)


def unlink_marked_vis_pair(marked_dir: Path, png_name: str) -> None:
    unlink_if_exists(marked_dir / png_name)
    unlink_if_exists((marked_dir / png_name).with_suffix(".json"))


def clear_dom_vis_outputs(marked_dir: Path, seg_dir: Path, dom_stem: str) -> None:
    """
    清理某个 DOM 的历史可视化输出，避免阈值/最小面积改变后与旧结果混杂。
    仅删除可视化与整图聚合文件，不影响 ``*_result.pkl`` 推理结果。
    """
    patterns = (
        f"{dom_stem}_tile_r*_c*_vis*.png",
        f"{dom_stem}_tile_r*_c*_vis*.json",
        f"{dom_stem}_whole_vis*.png",
        f"{dom_stem}_whole_vis*.json",
    )
    for pat in patterns:
        for p in marked_dir.glob(pat):
            unlink_if_exists(p)
    unlink_if_exists(seg_dir / f"{dom_stem}_whole_centers.json")
