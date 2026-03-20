"""
自定义 MMDetection 模块：TreeNet backbone 与 TREEFPN neck。
在加载 config 前必须先 import 本文件，或通过 config 的 custom_imports 引入。

用法一：在推理前手动导入
  import mmdet_custom_models  # 或 from mmdet_custom_models import *  # noqa
  # 再 init_detector(...)

用法二：在 config 中增加
  custom_imports = dict(imports=['mmdet_custom_models'], allow_failed_imports=False)
"""
from __future__ import annotations

import torch
import torch.nn as nn
from torch.nn.modules.batchnorm import _BatchNorm


def _build_norm_layer(norm_cfg: dict, num_features: int) -> nn.Module:
    if norm_cfg.get("type") == "BN":
        return nn.BatchNorm2d(num_features)
    raise NotImplementedError(norm_cfg)


class TreeNet(nn.Module):
    """占位 backbone：输出 4 层特征，通道为 [16, 40, 48, 576]，与 config 中 neck in_channels 一致。"""

    def __init__(
        self,
        arch: str = "small",
        in_channels: int = 3,
        out_indices: tuple[int, ...] = (0, 4, 8, 12),
        frozen_stages: int = -1,
        norm_cfg: dict | None = None,
        norm_eval: bool = True,
        **kwargs,
    ):
        super().__init__()
        self.out_indices = out_indices
        self.frozen_stages = frozen_stages
        self.norm_eval = norm_eval
        norm_cfg = norm_cfg or dict(type="BN", requires_grad=True)

        # 4 个 stage，输出通道与 TREEFPN in_channels 一致
        channels = [16, 40, 48, 576]
        layers = []
        prev_c = in_channels
        for i, c in enumerate(channels):
            layers.append(
                nn.Sequential(
                    nn.Conv2d(prev_c, c, kernel_size=3, stride=2, padding=1),
                    _build_norm_layer(norm_cfg, c),
                    nn.ReLU(inplace=True),
                    nn.Conv2d(c, c, kernel_size=3, stride=1, padding=1),
                    _build_norm_layer(norm_cfg, c),
                    nn.ReLU(inplace=True),
                )
            )
            prev_c = c
        self.stages = nn.ModuleList(layers)

    def forward(self, x: torch.Tensor) -> tuple[torch.Tensor, ...]:
        outs = []
        for i, stage in enumerate(self.stages):
            x = stage(x)
            if i in self.out_indices:
                outs.append(x)
        return tuple(outs)

    def train(self, mode: bool = True):
        super().train(mode)
        if self.norm_eval and mode:
            for m in self.modules():
                if isinstance(m, _BatchNorm):
                    m.eval()


class TREEFPN(nn.Module):
    """占位 neck：4 路输入 [16, 40, 48, 576]，5 路输出均为 32 通道，与 config 一致。"""

    def __init__(
        self,
        in_channels: list[int],
        out_channels: int = 32,
        num_outs: int = 5,
        start_level: int = 0,
        **kwargs,
    ):
        super().__init__()
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.num_outs = num_outs
        self.start_level = start_level

        self.lateral_convs = nn.ModuleList()
        self.fpn_convs = nn.ModuleList()
        for i in range(len(in_channels)):
            self.lateral_convs.append(
                nn.Conv2d(in_channels[i], out_channels, kernel_size=1)
            )
            self.fpn_convs.append(
                nn.Conv2d(out_channels, out_channels, kernel_size=3, padding=1)
            )
        # num_outs=5 时多一层，用最后一层再下采样
        if num_outs > len(in_channels):
            self.extra_convs = nn.ModuleList()
            for _ in range(num_outs - len(in_channels)):
                self.extra_convs.append(
                    nn.Sequential(
                        nn.Conv2d(out_channels, out_channels, kernel_size=3, stride=2, padding=1),
                        nn.ReLU(inplace=True),
                    )
                )
        else:
            self.extra_convs = nn.ModuleList()

    def forward(self, inputs: tuple[torch.Tensor, ...]) -> tuple[torch.Tensor, ...]:
        assert len(inputs) == len(self.in_channels)
        laterals = [lateral(inputs[i]) for i, lateral in enumerate(self.lateral_convs)]
        for i in range(len(laterals) - 1, 0, -1):
            size = laterals[i - 1].shape[2:]
            laterals[i - 1] = laterals[i - 1] + nn.functional.interpolate(
                laterals[i], size=size, mode="nearest"
            )
        outs = [self.fpn_convs[i](laterals[i]) for i in range(len(laterals))]
        for extra in self.extra_convs:
            outs.append(extra(outs[-1]))
        return tuple(outs)


def register_custom_modules():
    """向 mmdet 注册 TreeNet、TREEFPN（兼容 mmdet 2.x / 3.x）。"""
    # MMDet 3.x
    try:
        from mmdet.registry import MODELS
        if "TreeNet" not in MODELS.module_dict:
            MODELS.register_module(name="TreeNet", module=TreeNet)
        if "TREEFPN" not in MODELS.module_dict:
            MODELS.register_module(name="TREEFPN", module=TREEFPN)
        return
    except (ImportError, AttributeError):
        pass
    # MMDet 2.x
    try:
        from mmdet.models.builder import BACKBONES, NECKS
        if "TreeNet" not in BACKBONES.module_dict:
            BACKBONES.register_module(module=TreeNet)
        if "TREEFPN" not in NECKS.module_dict:
            NECKS.register_module(module=TREEFPN)
    except (ImportError, AttributeError):
        try:
            from mmdet.models import BACKBONES, NECKS
            BACKBONES.register_module(module=TreeNet)
            NECKS.register_module(module=TREEFPN)
        except Exception as e:
            raise ImportError(
                "无法注册 TreeNet/TREEFPN，请确认已安装 mmdet。若使用训练时的自定义代码，请先 import 该模块。"
            ) from e


# 导入时自动注册
register_custom_modules()
