#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""按 MMDetection 配置文件构建 TwoStageDetector，可选加载权重并做 dummy 前向。

在仓库 `Trees` 目录下运行::

    python run_model_from_config.py \\
        --config Models/20230430_224903_config3.py \\
        --checkpoint Models/20250416_001154_epoch36_latest.pth

需已安装 mmdet、mmcv（及 mmengine，若使用 MMDet 3.x）。
"""
from __future__ import annotations

import argparse
import sys
from pathlib import Path

import torch


def _ensure_trees_on_path() -> Path:
    root = Path(__file__).resolve().parent
    if str(root) not in sys.path:
        sys.path.insert(0, str(root))
    return root


def build_model(
    config_path: Path,
    checkpoint: Path | None,
    device: str,
):
    import mmdet_custom_models  # noqa: F401 — 注册 TreeNet / TREEFPN

    config_path = config_path.resolve()
    if not config_path.is_file():
        raise FileNotFoundError(f"配置文件不存在: {config_path}")


    # MMDetection 2.x + mmcv
    from mmcv import Config
    from mmcv.runner import load_checkpoint
    from mmdet.models import build_detector

    cfg = Config.fromfile(str(config_path))
    model = build_detector(
        cfg.model,
        # train_cfg=cfg.model.get("train_cfg"),
        # test_cfg=cfg.model.get("test_cfg"),
    )
    if checkpoint is not None and checkpoint.is_file():
        load_checkpoint(model, str(checkpoint), map_location="cpu", strict=True)
    model.to(device)
    model.eval()
    # mmdet 2.x 的推理入口（inference_detector）会访问 model.cfg
    # build_detector(model_cfg) 不一定会自动挂载 cfg，因此这里补上。
    model.cfg = cfg
    # 兼容性：有些代码依赖 dataset_meta / CLASSES
    if hasattr(cfg, "classes"):
        model.CLASSES = cfg.classes
    return model, cfg


def main() -> None:
    parser = argparse.ArgumentParser(description="按 config 构建检测模型并测试前向")
    parser.add_argument("--config", type=str, required=True, help="配置文件路径")
    parser.add_argument(
        "--checkpoint",
        type=str,
        default="",
        help="权重 .pth 路径，可省略（随机初始化）",
    )
    parser.add_argument("--device", type=str, default="cuda:0")
    parser.add_argument(
        "--image",
        type=str,
        default="",
        help="输入图片路径（可选；传了则进行推理并返回结果）",
    )
    parser.add_argument(
        "--out-dir",
        type=str,
        default="out",
        help="推理结果保存目录（可选）",
    )
    parser.add_argument(
        "--score-thr",
        type=float,
        default=0.3,
        help="置信度过滤阈值（仅用于结果摘要/保存）",
    )
    parser.add_argument(
        "--save-result",
        action="store_true",
        help="将推理结果保存为 result.pkl（不做可视化绘制）",
    )
    parser.add_argument(
        "--dummy-size",
        type=int,
        nargs=2,
        default=[1024, 1024],
        metavar=("H", "W"),
        help="dummy 输入高宽",
    )
    parser.add_argument(
        "--no-forward",
        action="store_true",
        help="仅构建模型，不做前向",
    )
    args = parser.parse_args()

    _ensure_trees_on_path()
    trees = Path(__file__).resolve().parent

    cfg_p = Path(args.config)
    if not cfg_p.is_file():
        cfg_p = trees / args.config

    ckpt_p: Path | None = None
    if args.checkpoint:
        ckpt_p = Path(args.checkpoint)
        if not ckpt_p.is_file():
            ckpt_p = trees / args.checkpoint
        if not ckpt_p.is_file():
            print(f"警告: 未找到权重文件，跳过加载: {args.checkpoint}")
            ckpt_p = None

    device = args.device
    if device.startswith("cuda") and not torch.cuda.is_available():
        print("CUDA 不可用，改用 cpu")
        device = "cpu"

    model, _cfg = build_model(cfg_p, ckpt_p, device)
    print(f"模型构建成功: {type(model).__name__}")

    if args.no_forward:
        return

    h, w = args.dummy_size
    dummy = torch.randn(1, 3, h, w, device=device)

    with torch.no_grad():
        # 1) 若提供 image：走真实推理
        if args.image:
            img_path = Path(args.image)
            if not img_path.is_file():
                img_path = (trees / args.image).resolve()
            if not img_path.is_file():
                raise FileNotFoundError(f"图片不存在: {args.image}")

            # tif 读取：优先 rasterio（通常最稳），失败再用 cv2，最后再把路径交给 mmdet 自己读
            ext = img_path.suffix.lower()
            img_for_infer = str(img_path)
            if ext in {".tif", ".tiff"}:
                img = None
                # 1) rasterio 读取（读多波段更稳）
                try:
                    import rasterio  # type: ignore

                    with rasterio.open(str(img_path)) as src:
                        data = src.read()
                    if data.ndim == 2:
                        data = data[None, ...]
                    # 取前 3 个波段作为 RGB（如果不是 RGB 数据，至少保持维度一致）
                    if data.shape[0] >= 3:
                        img = data[:3].transpose(1, 2, 0)
                    else:
                        img = (data[0] if data.shape[0] == 1 else data[-1])
                        img = (img[..., None]).repeat(3, axis=2)
                    # 归一化到 uint8（mmdet 读取通常期望 uint8）
                    if img.dtype != "uint8":
                        mn, mx = float(img.min()), float(img.max())
                        if mx > mn:
                            img = ((img.astype("float64") - mn) / (mx - mn) * 255.0).astype(
                                "uint8"
                            )
                        else:
                            img = img.astype("uint8")
                except Exception:
                    img = None

                # 2) rasterio 失败则用 cv2
                if img is None:
                    try:
                        import cv2  # type: ignore

                        raw = cv2.imread(str(img_path), cv2.IMREAD_UNCHANGED)
                        if raw is None:
                            raise FileNotFoundError(f"cv2 读取失败: {img_path}")
                        if raw.ndim == 2:
                            img = cv2.cvtColor(raw, cv2.COLOR_GRAY2RGB)
                        elif raw.shape[2] == 4:
                            img = cv2.cvtColor(raw[:, :, :3], cv2.COLOR_BGR2RGB)
                        else:
                            img = cv2.cvtColor(raw, cv2.COLOR_BGR2RGB)
                    except Exception:
                        img = None

                # 3) 都失败：交给 mmdet 自己读
                if img is not None:
                    img_for_infer = img

            # 推理：兼容 MMDet 2.x/3.x 的 inference_detector 返回值
            from mmdet.apis import inference_detector

            result = inference_detector(model, img_for_infer)

            # 结果摘要（尽量对齐 bbox/instance 两类返回）
            def _summarize(result_obj) -> dict:
                summary: dict = {}
                if isinstance(result_obj, tuple):
                    bbox_result = result_obj[0]
                    class_counts = []
                    class_kept = []
                    for b in bbox_result:
                        if b is None or len(b) == 0:
                            class_counts.append(0)
                            class_kept.append(0)
                            continue
                        class_counts.append(int(b.shape[0]))
                        if b.shape[1] >= 5:
                            kept = b[b[:, 4] >= args.score_thr]
                            class_kept.append(int(kept.shape[0]))
                        else:
                            class_kept.append(int(b.shape[0]))
                    summary["bbox_per_class"] = class_counts
                    summary["bbox_per_class_kept_thr"] = class_kept
                else:
                    pred = getattr(result_obj, "pred_instances", None)
                    if pred is not None and hasattr(pred, "bboxes") and hasattr(pred, "scores"):
                        scores = pred.scores.detach().cpu()
                        summary["num_bboxes"] = int(scores.shape[0])
                        summary["num_bboxes_kept_thr"] = int((scores >= args.score_thr).sum().item())
                    else:
                        summary["type"] = str(type(result_obj))
                return summary

            summary = _summarize(result)
            print("推理结果摘要:", summary)

            if args.save_result:
                out_dir = (trees / args.out_dir).resolve()
                out_dir.mkdir(parents=True, exist_ok=True)
                import pickle

                out_p = out_dir / f"{img_path.stem}_result.pkl"
                with open(out_p, "wb") as f:
                    pickle.dump(result, f)
                print(f"已保存推理结果: {out_p}")

            # 满足“推理完成返回结果”的需求：直接结束
            return

        if hasattr(model, "forward_dummy"):
            out = model.forward_dummy(dummy)
            if isinstance(out, torch.Tensor):
                print("forward_dummy 输出 shape:", tuple(out.shape))
            else:
                print("forward_dummy 输出:", type(out))
            

        if hasattr(model, "extract_feat"):
            try:
                out = model.extract_feat(dummy)
                print(
                    "extract_feat 输出层数:",
                    len(out) if isinstance(out, (tuple, list)) else "N/A",
                )
                if isinstance(out, (tuple, list)):
                    for i, t in enumerate(out):
                        if torch.is_tensor(t):
                            print(f"  [{i}] {tuple(t.shape)}")
                return
                
            except Exception as e:
                print("extract_feat 失败:", e)

        if hasattr(model, "backbone") and hasattr(model, "neck"):
            feats = model.backbone(dummy)
            feats = model.neck(feats)
            print("backbone+neck 输出层数:", len(feats))
            for i, t in enumerate(feats):
                print(f"  [{i}] {tuple(t.shape)}")
            return

        print("尝试 model(dummy) …")
        out = model(dummy)
        print("输出:", type(out))


if __name__ == "__main__":
    main()
