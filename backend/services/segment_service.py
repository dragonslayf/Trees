from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

from fastapi import HTTPException
from fastapi.responses import StreamingResponse

from storage.workspace_files import (
    clear_dom_vis_outputs,
    dom_tile_paths,
    marked_result_dir,
    segmentation_result_dir,
    unlink_marked_vis_pair,
)
from services.merge_service import (
    marked_vis_png_name,
    merge_tile_json_to_whole_json,
)


def marked_vis_outputs_ready(marked_dir: Path, png_name: str) -> bool:
    p = marked_dir / png_name
    return p.is_file() and p.with_suffix(".json").is_file()


def _run_subprocess_or_500(cmd: list[str], cwd: Path, timeout: int = 7200) -> None:
    try:
        r = subprocess.run(
            cmd,
            cwd=str(cwd),
            capture_output=True,
            text=True,
            timeout=timeout,
        )
    except subprocess.TimeoutExpired as e:
        raise HTTPException(status_code=504, detail="推理子进程超时") from e
    except Exception as e:
        raise HTTPException(status_code=500, detail=str(e)) from e
    if r.returncode != 0:
        tail = (r.stderr or r.stdout or "").strip()
        tail = tail[-4000:] if tail else "未知错误"
        raise HTTPException(status_code=500, detail=f"子进程失败: {tail}")


def _find_checkpoint(models_dir: Path) -> str | None:
    ckpts = sorted(models_dir.glob("*.pth"))
    return str(ckpts[0].resolve()) if ckpts else None


def _segment_model_config_path(default_seg_config: Path, models_dir: Path) -> Path:
    if default_seg_config.is_file():
        return default_seg_config
    cands = sorted(models_dir.glob("*config*.py"))
    cands = [p for p in cands if p.name != "run_model_from_config.py"]
    if cands:
        return cands[0]
    raise HTTPException(
        status_code=500,
        detail=f"未找到分割 config，请将配置文件放在 {models_dir} 下",
    )


def run_segment_stream(
    *,
    use_data_dir: Path,
    use_dom: str,
    overwrite: bool,
    score_thr: float,
    min_canopy_area_m2: float,
    models_dir: Path,
    run_model_script: Path,
    visualize_script: Path,
    default_seg_config: Path,
) -> StreamingResponse:
    if not run_model_script.is_file():
        raise HTTPException(status_code=500, detail=f"未找到脚本: {run_model_script}")
    if not visualize_script.is_file():
        raise HTTPException(status_code=500, detail=f"未找到脚本: {visualize_script}")

    stem = Path(use_dom).stem
    tiles = dom_tile_paths(use_data_dir, stem)
    if not tiles:
        raise HTTPException(
            status_code=400,
            detail="未找到切片 TIFF，请先在数据管理中完成 DOM 切分",
        )

    cfg_path = _segment_model_config_path(default_seg_config, models_dir)
    pkl_dir = segmentation_result_dir(use_data_dir)
    marked_dir = marked_result_dir(use_data_dir)
    pkl_dir.mkdir(parents=True, exist_ok=True)
    marked_dir.mkdir(parents=True, exist_ok=True)

    if not overwrite:
        for t in tiles:
            if (pkl_dir / f"{t.stem}_result.pkl").is_file():
                raise HTTPException(
                    status_code=409,
                    detail="已存在分割结果（pkl），如需覆盖请传 overwrite=true 或在前端确认后重试",
                )

    ckpt = _find_checkpoint(models_dir)
    cfg_rel = cfg_path.name
    total = len(tiles)

    def ndjson_stream():
        try:
            yield json.dumps(
                {"type": "progress", "n": 0, "total": total},
                ensure_ascii=False,
            ) + "\n"
            processed = 0
            for t in tiles:
                pkl_path = pkl_dir / f"{t.stem}_result.pkl"
                vis_png = marked_vis_png_name(t.stem, score_thr, min_canopy_area_m2)
                vis_path = marked_dir / vis_png
                cmd = [
                    sys.executable,
                    str(run_model_script.resolve()),
                    "--config",
                    cfg_rel,
                    "--image",
                    str(t.resolve()),
                    "--out-dir",
                    str(pkl_dir),
                    "--save-result",
                    "--score-thr",
                    str(score_thr),
                ]
                if ckpt:
                    cmd.extend(["--checkpoint", ckpt])
                _run_subprocess_or_500(cmd, cwd=models_dir)

                if not pkl_path.is_file():
                    raise HTTPException(
                        status_code=500,
                        detail=f"推理后未生成 pkl: {pkl_path.name}",
                    )

                if marked_vis_outputs_ready(marked_dir, vis_png):
                    processed += 1
                else:
                    unlink_marked_vis_pair(marked_dir, vis_png)
                    vcmd = [
                        sys.executable,
                        str(visualize_script.resolve()),
                        "--pkl",
                        str(pkl_path.resolve()),
                        "--image",
                        str(t.resolve()),
                        "--out",
                        str(vis_path.resolve()),
                        "--score-thr",
                        str(score_thr),
                        "--min-canopy-area-m2",
                        str(min_canopy_area_m2),
                    ]
                    _run_subprocess_or_500(vcmd, cwd=models_dir)
                    processed += 1
                yield json.dumps(
                    {"type": "progress", "n": processed, "total": total},
                    ensure_ascii=False,
                ) + "\n"
            whole_json: str | None = None
            whole_mark_png: str | None = None
            whole_json_error: str | None = None
            try:
                p_json, p_mark = merge_tile_json_to_whole_json(
                    dom_image=use_data_dir / use_dom,
                    seg_result_dir=pkl_dir,
                    marked_dir=marked_dir,
                    score_thr=score_thr,
                    min_canopy_area_m2=min_canopy_area_m2,
                    tile=800,
                    overlap=200,
                )
                whole_json = str(p_json)
                whole_mark_png = str(p_mark)
            except Exception as e:
                whole_json_error = str(e)
            done_payload: dict = {
                "type": "done",
                "ok": True,
                "processed": processed,
                "data_dir": str(use_data_dir),
                "segmentation_result_dir": str(pkl_dir),
                "marked_result_dir": str(marked_dir),
                "dom_filename": use_dom,
                "score_thr": score_thr,
                "min_canopy_area_m2": min_canopy_area_m2,
            }
            if whole_json:
                done_payload["whole_centers_json"] = whole_json
            if whole_mark_png:
                done_payload["whole_mark_png"] = whole_mark_png
            if whole_json_error:
                done_payload["whole_centers_json_error"] = whole_json_error
            yield json.dumps(done_payload, ensure_ascii=False) + "\n"
        except HTTPException as e:
            yield json.dumps(
                {"type": "error", "detail": str(e.detail)},
                ensure_ascii=False,
            ) + "\n"
        except Exception as e:
            yield json.dumps(
                {"type": "error", "detail": str(e)},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        ndjson_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )


def regenerate_vis_stream(
    *,
    use_data_dir: Path,
    use_dom: str,
    score_thr: float,
    min_canopy_area_m2: float,
    models_dir: Path,
    visualize_script: Path,
) -> StreamingResponse:
    if not visualize_script.is_file():
        raise HTTPException(status_code=500, detail=f"未找到脚本: {visualize_script}")

    stem = Path(use_dom).stem
    tiles = dom_tile_paths(use_data_dir, stem)
    if not tiles:
        raise HTTPException(
            status_code=400,
            detail="未找到 DOM 切片，请先在数据管理中完成切分",
        )

    pkl_dir = segmentation_result_dir(use_data_dir)
    marked_dir = marked_result_dir(use_data_dir)
    marked_dir.mkdir(parents=True, exist_ok=True)
    tiles_with_pkl = [t for t in tiles if (pkl_dir / f"{t.stem}_result.pkl").is_file()]
    total = len(tiles_with_pkl)

    def ndjson_stream():
        try:
            clear_dom_vis_outputs(marked_dir, pkl_dir, stem)
            yield json.dumps(
                {"type": "progress", "n": 0, "total": total},
                ensure_ascii=False,
            ) + "\n"
            regenerated = 0
            for t in tiles_with_pkl:
                pkl_path = pkl_dir / f"{t.stem}_result.pkl"
                vis_png = marked_vis_png_name(t.stem, score_thr, min_canopy_area_m2)
                vis_path = marked_dir / vis_png
                if marked_vis_outputs_ready(marked_dir, vis_png):
                    regenerated += 1
                else:
                    unlink_marked_vis_pair(marked_dir, vis_png)
                    vcmd = [
                        sys.executable,
                        str(visualize_script.resolve()),
                        "--pkl",
                        str(pkl_path.resolve()),
                        "--image",
                        str(t.resolve()),
                        "--out",
                        str(vis_path.resolve()),
                        "--score-thr",
                        str(score_thr),
                        "--min-canopy-area-m2",
                        str(min_canopy_area_m2),
                    ]
                    _run_subprocess_or_500(vcmd, cwd=models_dir)
                    regenerated += 1
                yield json.dumps(
                    {"type": "progress", "n": regenerated, "total": total},
                    ensure_ascii=False,
                ) + "\n"
            whole_json: str | None = None
            whole_mark_png: str | None = None
            whole_json_error: str | None = None
            try:
                p_json, p_mark = merge_tile_json_to_whole_json(
                    dom_image=use_data_dir / use_dom,
                    seg_result_dir=pkl_dir,
                    marked_dir=marked_dir,
                    score_thr=score_thr,
                    min_canopy_area_m2=min_canopy_area_m2,
                    tile=800,
                    overlap=200,
                )
                whole_json = str(p_json)
                whole_mark_png = str(p_mark)
            except Exception as e:
                whole_json_error = str(e)
            done_payload: dict = {
                "type": "done",
                "ok": True,
                "regenerated": regenerated,
                "data_dir": str(use_data_dir),
                "segmentation_result_dir": str(pkl_dir),
                "marked_result_dir": str(marked_dir),
                "dom_filename": use_dom,
                "score_thr": score_thr,
                "min_canopy_area_m2": min_canopy_area_m2,
            }
            if whole_json:
                done_payload["whole_centers_json"] = whole_json
            if whole_mark_png:
                done_payload["whole_mark_png"] = whole_mark_png
            if whole_json_error:
                done_payload["whole_centers_json_error"] = whole_json_error
            yield json.dumps(done_payload, ensure_ascii=False) + "\n"
        except HTTPException as e:
            yield json.dumps(
                {"type": "error", "detail": str(e.detail)},
                ensure_ascii=False,
            ) + "\n"
        except Exception as e:
            yield json.dumps(
                {"type": "error", "detail": str(e)},
                ensure_ascii=False,
            ) + "\n"

    return StreamingResponse(
        ndjson_stream(),
        media_type="application/x-ndjson",
        headers={
            "Cache-Control": "no-store",
            "X-Accel-Buffering": "no",
        },
    )
