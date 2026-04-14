#!/user/bin/env python
# -*- coding: utf-8 -*-
# @Time     : 2022/12/24 12:38
# @Author   : Bin Yang
# @File     : TreeFPN.py
import torch
import torch.nn as nn
from mmcv.cnn import ConvModule
from mmcv.ops.merge_cells import GlobalPoolingCell, SumCell, ConcatCell
from mmcv.runner import BaseModule, ModuleList

from se_layer import SELayer
# from ..utils.mulse_layer import BiSELayer, MSSELayer
# from ..utils.CBAM_layer import CBAM
# from ..utils.mulCBAM_layer import BBCBAM, BMCBAM, MMCBAM, MBCBAM

# from ..builder import NECKS
# from ..builder import NECKS

def _register_tree_fpn():
    """注册到 MMDetection 2.x（NECKS）或 3.x（MODELS），未安装 mmdet 时静默跳过。"""
    try:
        from mmdet.registry import MODELS

        if 'TREEFPN' not in MODELS.module_dict:
            MODELS.register_module(name='TREEFPN', module=TREEFPN)
        return
    except (ImportError, AttributeError):
        pass
    try:
        from mmdet.models.builder import NECKS as _REG
    except (ImportError, AttributeError):
        try:
            from mmdet.models import NECKS as _REG
        except (ImportError, AttributeError):
            return
    if 'TREEFPN' not in _REG.module_dict:
        _REG.register_module(module=TREEFPN)


class TREEFPN(BaseModule):
    """TREEFPN.

    Implementation of `TREEFPN: Learning Scalable Feature Pyramid Architecture


    Args:
        in_channels (List[int]): Number of input channels per scale.
        out_channels (int): Number of output channels (used at each scale)
        num_outs (int): Number of output scales.
        stack_times (int): The number of times the pyramid architecture will
            be stacked.
        start_level (int): Index of the start input backbone level used to
            build the feature pyramid. Default: 0.
        end_level (int): Index of the end input backbone level (exclusive) to
            build the feature pyramid. Default: -1, which means the last level.
        add_extra_convs (bool): It decides whether to add conv
            layers on top of the original feature maps. Default to False.
            If True, its actual mode is specified by `extra_convs_on_inputs`.
        init_cfg (dict or list[dict], optional): Initialization config dict.
    """

    def __init__(self,
                 in_channels,
                 out_channels,
                 num_outs,
                 stack_times=1,
                 start_level=0,
                 end_level=-1,
                 # init=0.4-1,
                 with_se=False,
                 se_type='SE',
                 add_extra_convs=False,
                 norm_cfg=dict(type='BN', eps=0.001, momentum=0.01),
                 init_cfg=[
                            dict(type='Caffe2Xavier', layer='Conv2d'),
                            dict(type='Constant', layer=['BatchNorm2d'], val=1)
                 ]):
        super(TREEFPN, self).__init__(init_cfg)
        assert isinstance(in_channels, list)
        self.in_channels = in_channels
        self.out_channels = out_channels
        self.num_ins = len(in_channels)  # num of input feature levels
        self.num_outs = num_outs  # num of output feature levels
        self.stack_times = stack_times
        self.norm_cfg = norm_cfg
        self.with_se = with_se
        self.se_type = se_type

        if end_level == -1:
            self.backbone_end_level = self.num_ins
            assert num_outs >= self.num_ins - start_level
        else:
            # if end_level < inputs, no extra level is allowed
            self.backbone_end_level = end_level
            assert end_level <= len(in_channels)
            assert num_outs == end_level - start_level
        self.start_level = start_level
        self.end_level = end_level
        self.add_extra_convs = add_extra_convs

        # add lateral connections
        self.lateral_convs = nn.ModuleList()
        for i in range(self.start_level, self.backbone_end_level):
            l_conv = ConvModule(
                in_channels[i],
                out_channels,
                1,
                norm_cfg=None,
                act_cfg=None)
            self.lateral_convs.append(l_conv)

        # add extra downsample layers (stride-2 pooling or conv)
        # extra_levels = num_outs - self.backbone_end_level + self.start_level
        extra_levels = 5 - self.backbone_end_level + self.start_level
        self.extra_downsamples = nn.ModuleList()
        for i in range(extra_levels):
            extra_conv = ConvModule(
                out_channels, out_channels, 1, norm_cfg=None, act_cfg=None)
            self.extra_downsamples.append(
                nn.Sequential(extra_conv, nn.MaxPool2d(2, 2)))

        # add weights
        #weighted
        # self.ww = []
        # self.relu6 = []
        # for _ in range(self.stack_times):
        #     self.ww.append(nn.Parameter(torch.Tensor(2, 4-1).fill_(init), requires_grad=True))
        #     self.relu6.append(nn.ReLU6())
        # self.depthwise_conv = nn.Sequential(
        #                 ConvModule(
        #                     out_channels,
        #                     out_channels,
        #                     4,
        #                     padding=1,
        #                     groups=out_channels,
        #                     norm_cfg=None,
        #                     inplace=False),
        #                 ConvModule(
        #                     out_channels,
        #                     out_channels,
        #                     1,
        #                     norm_cfg=norm_cfg,
        #                     inplace=False)
        #             )
        # add fused conv to last layer
        self.treefpn_convs = nn.ModuleList()
        for _ in range(self.stack_times):
            for i in range(3):
                if self.with_se:
                    se_cfg = dict(
                        channels=out_channels*2,
                        ratio=4,
                        act_cfg=(dict(type='ReLU'),
                                 dict(
                                     type='HSigmoid',
                                     bias=3,
                                     divisor=6,
                                     min_value=0,
                                     max_value=1)))
                    if self.se_type == 'SE':
                        self.se = SELayer(**se_cfg)
                    elif self.se_type == 'BISE':
                        self.se = BiSELayer(**se_cfg)
                    elif self.se_type == 'MSSE':
                        self.se = MSSELayer(**se_cfg)
                    elif self.se_type == 'CBAM':
                        self.se = CBAM(**se_cfg)
                    elif self.se_type == 'BBCBAM':
                        self.se = BBCBAM(**se_cfg)
                    elif self.se_type == 'BMCBAM':
                        self.se = BMCBAM(**se_cfg)
                    elif self.se_type == 'MMCBAM':
                        self.se = MMCBAM(**se_cfg)
                    elif self.se_type == 'MBCBAM':
                        self.se = MBCBAM(**se_cfg)
                    else:
                        raise ValueError
                    down_conv = nn.Sequential(
                        self.se,
                        ConvModule(
                            out_channels*2,
                            out_channels,
                            kernel_size=1,
                            stride=1,
                            padding=0,
                            norm_cfg=norm_cfg,
                            inplace=False)
                    )
                else:
                    down_conv = ConvModule(
                            out_channels*2,
                            out_channels,
                            kernel_size=1,
                            stride=1,
                            padding=0,
                            norm_cfg=norm_cfg,
                            inplace=False)
                self.treefpn_convs.append(down_conv)
        # add cross stage
        # self.cross_stages = ModuleList()
        # for i in range(self.stack_times):
        #     c_stage = nn.ModuleDict()
        #     # gp(p3, p3_t) -> p3
        #     # c_stage['gp_33_3'] = GlobalPoolingCell(
        #     #     in_channels=out_channels,
        #     #     out_channels=out_channels,
        #     #     out_norm_cfg=None)
        #     # c_stage['p3_out'] = self.treefpn_convs[4-1 * i + 0]
        #     # cat(p4, p4_t) -> p4
        #     c_stage['cat_44_4'] = ConcatCell(
        #         in_channels=out_channels,
        #         out_channels=out_channels,
        #         out_norm_cfg=None)
        #     c_stage['p4_out'] = self.treefpn_convs[2 * i + 0]
        #     # cat(p5, p5_t) -> p5
        #     # c_stage['cat_55_5'] = ConcatCell(
        #     #     in_channels=out_channels,
        #     #     out_channels=out_channels,
        #     #     out_norm_cfg=None)
        #     # c_stage['p5_out'] = self.treefpn_convs[4-1 * i + 2]
        #     # cat(p6, p6_t) -> p6
        #     c_stage['cat_66_6'] = ConcatCell(
        #         in_channels=out_channels,
        #         out_channels=out_channels,
        #         out_norm_cfg=None)
        #     c_stage['p6_out'] = self.treefpn_convs[2 * i + 1]
        #     # gp(p7, p7_t) -> p7
        #     # c_stage['gp_77_7'] = GlobalPoolingCell(
        #     #     in_channels=out_channels,
        #     #     out_channels=out_channels,
        #     #     out_norm_cfg=None)
        #     # c_stage['p7_out'] = self.treefpn_convs[4-1 * i + 5]
        #     self.cross_stages.append(c_stage)


        # add NAS FPN connections
        self.fpn_stages = ModuleList()
        for _ in range(self.stack_times*2):
            stage = nn.ModuleDict()
            # gp(p6, p4) -> p4_1
            stage['gp_64_4'] = GlobalPoolingCell(
                in_channels=out_channels,
                out_channels=out_channels,
                out_norm_cfg=None)
            # sum(p4_1, p4) -> p4_2
            stage['sum_44_4'] = SumCell(
                in_channels=out_channels,
                out_channels=out_channels,
                out_norm_cfg=None)
            # sum(p4_2, p3) -> p3_out
            stage['sum_43_3'] = SumCell(
                in_channels=out_channels,
                out_channels=out_channels,
                out_norm_cfg=None)
            # sum(p3_out, p4_2) -> p4_out
            stage['sum_34_4'] = SumCell(
                in_channels=out_channels,
                out_channels=out_channels,
                out_norm_cfg=None)
            # sum(p5, gp(p4_out, p3_out)) -> p5_out
            stage['gp_43_5'] = GlobalPoolingCell(with_out_conv=False)
            stage['sum_55_5'] = SumCell(
                in_channels=out_channels,
                out_channels=out_channels,
                out_norm_cfg=None)
            # sum(p7, gp(p5_out, p4_2)) -> p7_out
            stage['gp_54_7'] = GlobalPoolingCell(with_out_conv=False)
            stage['sum_77_7'] = SumCell(
                in_channels=out_channels,
                out_channels=out_channels,
                out_norm_cfg=None)
            # gp(p7_out, p5_out) -> p6_out
            stage['gp_75_6'] = GlobalPoolingCell(
                in_channels=out_channels,
                out_channels=out_channels,
                out_norm_cfg=None)
            self.fpn_stages.append(stage)

    def forward(self, inputs):
        """Forward function."""
        # build P3-P5
        feats = [
            lateral_conv(inputs[i + self.start_level])
            for i, lateral_conv in enumerate(self.lateral_convs)
        ]
        # build P6-P7 on top of P5
        for downsample in self.extra_downsamples:
            feats.append(downsample(feats[-1]))

        p3, p4, p5, p6, p7 = feats
        # _, p4_t, _, p6_t, _ = feats

        # for i in range(len(self.ww)):
        #     self.ww[i] = self.relu6[i](self.ww[i])
        #     self.ww[i] /= torch.sum(self.ww[i], dim=0) + eps #normalize

        jj = 0
        for i, stage in enumerate(self.fpn_stages):
            # gp(p6, p4) -> p4_1
            p4_1 = stage['gp_64_4'](p6, p4, out_size=p4.shape[-2:])
            # sum(p4_1, p4) -> p4_2
            p4_2 = stage['sum_44_4'](p4_1, p4, out_size=p4.shape[-2:])
            # sum(p4_2, p3) -> p3_out
            p3 = stage['sum_43_3'](p4_2, p3, out_size=p3.shape[-2:])
            # sum(p3_out, p4_2) -> p4_out
            p4 = stage['sum_34_4'](p3, p4_2, out_size=p4.shape[-2:])
            # sum(p5, gp(p4_out, p3_out)) -> p5_out
            p5_tmp = stage['gp_43_5'](p4, p3, out_size=p5.shape[-2:])
            p5 = stage['sum_55_5'](p5, p5_tmp, out_size=p5.shape[-2:])
            # sum(p7, gp(p5_out, p4_2)) -> p7_out
            p7_tmp = stage['gp_54_7'](p5, p4_2, out_size=p7.shape[-2:])
            p7 = stage['sum_77_7'](p7, p7_tmp, out_size=p7.shape[-2:])
            # gp(p7_out, p5_out) -> p6_out
            p6 = stage['gp_75_6'](p7, p5, out_size=p6.shape[-2:])
            ft = [p3, p4, p5, p6, p7]

            if (i % 2) != 0:
                # for c, stage_c in enumerate(self.cross_stages):
                #     # p3 = stage_c['p3_out'](stage_c['gp_33_3'](p3_t, p3, out_size=p3.shape[-2:]))
                #     p4 = stage_c['p4_out'](stage_c['cat_44_4'](p4_t, p4, out_size=p4.shape[-2:]))
                #     # p5 = stage_c['p5_out'](stage_c['cat_55_5'](p5_t, p5, out_size=p5.shape[-2:]))
                #     p6 = stage_c['p6_out'](stage_c['cat_66_6'](p6_t, p6, out_size=p6.shape[-2:]))
                #     p4_t, p6_t = tuple([p4, p6])
                #     # p7 = stage_c['p7_out'](stage_c['gp_77_7'](p7_t, p7, out_size=p7.shape[-2:]))
                for kk in range(3):
                    feats[kk+1] = self.treefpn_convs[jj](torch.cat((feats[kk+1], ft[kk+1]), 1))
                    # feats[kk] = self.treefpn_convs[jj](torch.cat((feats[kk], ft[kk]), 1))
                    # feats[kk] = feats[kk] + ft[kk]
                    jj = jj + 1
                _, p4, p5, p6, _ = feats

        feats = (p3, p4, p5, p6, p7)
        return feats[:self.num_outs]

        # return p3, p4, p5, p6, p7


_register_tree_fpn()
