"""
使用 20230430_224903_config3.py 与 20250416_001154_epoch36_latest.pth
对 Larch-Dataset 下的 .tif 影像做实例分割推理，并保存可视化与检测结果。

依赖：需已安装 mmdet（及包含 TreeNet、TREEFPN 的扩展或同结构代码），
     并保证 config 中自定义模块可被导入。

运行示例（在项目根目录）：
  python inference_larch.py
  python inference_larch.py --config 20230430_224903_config3.py --checkpoint 20250416_001154_epoch36_latest.pth --img-dir Larch-Dataset --out-dir inference_out
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

import numpy as np


def read_tif_as_rgb(path: Path) -> np.ndarray:
    """将 .tif 读成 (H, W, 3) uint8 RGB，供 mmdet 使用。"""
    try:
        import rasterio
        with rasterio.open(path) as src:
            data = src.read()
        if data.ndim == 2:
            data = data[np.newaxis, ...]
        if data.shape[0] >= 3:
            rgb = data[:3].transpose(1, 2, 0)
        else:
            rgb = np.stack([data[0]] * 3, axis=-1)
        if rgb.dtype != np.uint8:
            mn, mx = rgb.min(), rgb.max()
            if mx > mn:
                rgb = ((rgb.astype(np.float64) - mn) / (mx - mn) * 255).astype(np.uint8)
            else:
                rgb = np.zeros_like(rgb, dtype=np.uint8)
        return np.ascontiguousarray(rgb)
    except Exception:
        pass
    try:
        import cv2
        img = cv2.imread(str(path))
        if img is None:
            raise FileNotFoundError(f"无法读取: {path}")
        return cv2.cvtColor(img, cv2.COLOR_BGR2RGB)
    except Exception as e:
        raise RuntimeError(f"读取 {path} 失败，请安装 rasterio 或 opencv-python: {e}") from e


def main():
    parser = argparse.ArgumentParser(description="Larch-Dataset 实例分割推理")
    parser.add_argument("--config", type=str, default="20230430_224903_config3.py", help="MMDet 配置文件路径")
    parser.add_argument("--checkpoint", type=str, default="20250416_001154_epoch36_latest.pth", help="权重文件路径")
    parser.add_argument("--img-dir", type=str, default="Larch-Dataset", help=".tif 图像所在目录")
    parser.add_argument("--out-dir", type=str, default="inference_out", help="可视化与结果输出目录")
    parser.add_argument("--device", type=str, default="cuda:0", help="cuda:0 或 cpu")
    parser.add_argument("--score-thr", type=float, default=0.3, help="置信度阈值")
    parser.add_argument("--max-per-image", type=int, default=200, help="每张图最多保留实例数")
    parser.add_argument("--no-strict", action="store_true", help="加载权重时 strict=False（仅当 backbone/neck 与权重不匹配时用，结果可能无效）")
    args = parser.parse_args()

    root = Path(__file__).resolve().parent
    config_path = root / args.config
    checkpoint_path = root / args.checkpoint
    img_dir = root / args.img_dir
    out_dir = root / args.out_dir
    out_dir.mkdir(parents=True, exist_ok=True)

    if not config_path.is_file():
        raise SystemExit(f"配置文件不存在: {config_path}")
    if not checkpoint_path.is_file():
        raise SystemExit(f"权重文件不存在: {checkpoint_path}")
    if not img_dir.is_dir():
        raise SystemExit(f"图像目录不存在: {img_dir}")

    tif_list = sorted(img_dir.glob("*.tif"))
    if not tif_list:
        raise SystemExit(f"未在 {img_dir} 下找到 .tif 文件")

    try:
        import mmdet_custom_models  # noqa: F401 注册 TreeNet、TREEFPN
    except ImportError:
        pass

    try:
        from mmdet.apis import init_detector, inference_detector
    except ImportError as e:
        raise SystemExit(
            "未检测到 mmdet，请先安装 MMDetection 及包含 TreeNet、TREEFPN 的代码后再运行。\n"
            f"ImportError: {e}"
        ) from e

    if args.no_strict:
        # 使用 strict=False 加载，避免 backbone/neck 与占位实现不匹配时报错（此时 backbone/neck 未加载，推理结果无效）
        from mmengine.config import Config
        from mmengine.registry import init_default_scope
        from mmdet.registry import MODELS
        from mmengine.runner import load_checkpoint
        init_default_scope("mmdet")
        cfg = Config.fromfile(str(config_path))
        model = MODELS.build(cfg.model)
        load_checkpoint(model, str(checkpoint_path), strict=False)
        model.cfg = cfg
        model.to(args.device)
        model.eval()
        print("警告: 已使用 --no-strict 加载，部分参数未加载，推理结果可能无效。请使用训练时的 TreeNet/TREEFPN 实现。")
    else:
        model = init_detector(str(config_path), str(checkpoint_path), device=args.device)

    # MMDet 3.x 使用 Visualizer，不再提供 show_result_pyplot
    visualizer = None
    try:
        from mmdet.registry import VISUALIZERS
        if hasattr(model, "cfg") and getattr(model.cfg, "visualizer", None):
            visualizer = VISUALIZERS.build(model.cfg.visualizer)
            visualizer.dataset_meta = getattr(model, "dataset_meta", None) or {}
    except Exception:
        pass

    def save_vis_fallback(img: np.ndarray, dets: np.ndarray, vis_path: str) -> None:
        """无 mmdet 可视化时用 matplotlib 绘制 bbox 并保存。"""
        import matplotlib
        matplotlib.use("Agg")
        import matplotlib.pyplot as plt
        fig, ax = plt.subplots(1, 1, figsize=(10, 10))
        ax.imshow(img)
        for row in dets:
            x1, y1, x2, y2, sc = row[:5]
            ax.add_patch(plt.Rectangle((x1, y1), x2 - x1, y2 - y1, fill=False, color="lime", linewidth=2))
            ax.text(x1, max(0, y1 - 5), f"{sc:.2f}", color="white", fontsize=8)
        ax.axis("off")
        plt.savefig(vis_path, bbox_inches="tight", dpi=150)
        plt.close()

    all_results = []
    for p in tif_list:
        img = read_tif_as_rgb(p)
        result = inference_detector(model, img)

        # 兼容 MMDet 2.x (bbox_result, segm_result) 与 3.x (DetDataSample)
        if isinstance(result, tuple):
            bbox_result, _ = result
            dets = np.vstack(bbox_result) if bbox_result and np.size(bbox_result[0]) else np.zeros((0, 5))
        else:
            pred = getattr(result, "pred_instances", None)
            if pred is not None and hasattr(pred, "bboxes") and hasattr(pred, "scores"):
                bboxes = pred.bboxes.cpu().numpy()
                scores = pred.scores.cpu().numpy()
                dets = np.hstack([bboxes, scores[:, None]]) if bboxes.size else np.zeros((0, 5))
            else:
                dets = np.zeros((0, 5))
        scores = dets[:, -1] if dets.size else np.array([])
        keep = scores >= args.score_thr
        dets = dets[keep] if dets.size else dets
        if len(dets) > args.max_per_image:
            order = np.argsort(-dets[:, -1])[: args.max_per_image]
            dets = dets[order]

        out_name = p.stem
        vis_path = out_dir / f"{out_name}_vis.png"
        res_list = []
        for row in dets:
            x1, y1, x2, y2, sc = row.tolist()
            res_list.append({"bbox": [round(x1, 2), round(y1, 2), round(x2, 2), round(y2, 2)], "score": round(sc, 4)})
        all_results.append({"image": p.name, "detections": res_list})

        # 可视化：优先 MMDet 3.x Visualizer，其次 model.show_result，最后自绘
        saved = False
        if visualizer is not None:
            try:
                visualizer.add_datasample(
                    name="vis",
                    image=img,
                    data_sample=result,
                    draw_gt=False,
                    out_file=str(vis_path),
                    pred_score_thr=args.score_thr,
                )
                saved = True
            except Exception:
                pass
        if not saved and hasattr(model, "show_result"):
            try:
                model.show_result(img, result, score_thr=args.score_thr, out_file=str(vis_path))
                saved = True
            except Exception:
                pass
        if not saved:
            save_vis_fallback(img, dets, str(vis_path))

    with open(out_dir / "results.json", "w", encoding="utf-8") as f:
        json.dump(all_results, f, ensure_ascii=False, indent=2)

    print(f"推理完成: 共 {len(tif_list)} 张 .tif，结果与可视化已写入 {out_dir}")
    print(f"检测结果汇总: {out_dir / 'results.json'}")


if __name__ == "__main__":
    main()
