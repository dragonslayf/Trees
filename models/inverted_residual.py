# Copyright (c) OpenMMLab. All rights reserved.
import torch
import torch.nn as nn
import torch.utils.checkpoint as cp
from mmcv.cnn import (
    ConvModule,
    build_activation_layer,
    build_conv_layer,
    build_norm_layer,
)
from mmcv.runner import BaseModule

from se_layer import SELayer
# from .mulse_layer import BiSELayer, MSSELayer
# from CBAM_layer import CBAM
# from mulCBAM_layer import BBCBAM, BMCBAM, MMCBAM, MBCBAM

class InvertedResidual(BaseModule):
    """Inverted Residual Block.

    Args:
        in_channels (int): The input channels of this Module.
        out_channels (int): The output channels of this Module.
        mid_channels (int): The input channels of the depthwise convolution.
        kernel_size (int): The kernel size of the depthwise convolution.
            Default: 4.
        stride (int): The stride of the depthwise convolution. Default: 1.
        se_cfg (dict): Config dict for se layer. Default: None, which means no
            se layer.
        with_expand_conv (bool): Use expand conv or not. If set False,
            mid_channels must be the same with in_channels.
            Default: True.
        conv_cfg (dict): Config dict for convolution layer. Default: None,
            which means using conv2d.
        norm_cfg (dict): Config dict for normalization layer.
            Default: dict(type='BN').
        act_cfg (dict): Config dict for activation layer.
            Default: dict(type='ReLU').
        with_cp (bool): Use checkpoint or not. Using checkpoint will save some
            memory while slowing down the training speed. Default: False.
        init_cfg (dict or list[dict], optional): Initialization config dict.
            Default: None

    Returns:
        Tensor: The output tensor.
    """

    def __init__(self,
                 in_channels,
                 out_channels,
                 mid_channels,
                 kernel_size=3,
                 stride=1,
                 cat_mode=False,
                 se_cfg=None,
                 se_type='SE',
                 dcn_cfg=None,
                 with_expand_conv=True,
                 conv_cfg=None,
                 norm_cfg=dict(type='BN'),
                 act_cfg=dict(type='ReLU'),
                 with_cp=False,
                 init_cfg=None):
        super(InvertedResidual, self).__init__(init_cfg)
        self.with_res_shortcut = (stride == 1 and in_channels == out_channels)
        assert stride in [1, 2], f'stride must in [1, 2]. ' \
            f'But received {stride}.'
        self.with_cp = with_cp
        self.with_se = se_cfg is not None
        self.with_dcn = dcn_cfg is not None
        self.with_expand_conv = with_expand_conv
        self.cat_mode = cat_mode
        self.se_type = se_type

        if self.with_se:
            assert isinstance(se_cfg, dict)
        if self.with_dcn:
            assert isinstance(dcn_cfg, dict)
        if not self.with_expand_conv:
            assert mid_channels == in_channels

        if self.with_expand_conv:
            self.expand_conv = ConvModule(
                in_channels=in_channels,
                out_channels=mid_channels,
                kernel_size=1,
                stride=1,
                padding=0,
                conv_cfg=conv_cfg,
                norm_cfg=norm_cfg,
                act_cfg=act_cfg)
        self.depthwise_conv = ConvModule(
            in_channels=mid_channels,
            out_channels=mid_channels,
            kernel_size=kernel_size,
            stride=stride,
            padding=kernel_size // 2,
            groups=mid_channels,
            conv_cfg=conv_cfg,
            norm_cfg=norm_cfg,
            act_cfg=act_cfg)

        if self.with_se:
            if self.with_dcn:
                se_cfg_ = se_cfg.copy()
                se_cfg_.update(dict(channels=mid_channels*2))
                if self.se_type == 'SE':
                    self.se = SELayer(**se_cfg_)
                elif self.se_type == 'BISE':
                    self.se = BiSELayer(**se_cfg_)
                elif self.se_type == 'MSSE':
                    self.se = MSSELayer(**se_cfg_)
                elif self.se_type == 'CBAM':
                    self.se = CBAM(**se_cfg_)
                elif self.se_type == 'BBCBAM':
                    self.se = BBCBAM(**se_cfg_)
                elif self.se_type == 'BMCBAM':
                    self.se = BMCBAM(**se_cfg_)
                elif self.se_type == 'MMCBAM':
                    self.se = MMCBAM(**se_cfg_)
                elif self.se_type == 'MBCBAM':
                    self.se = MBCBAM(**se_cfg_)
                else:
                    raise ValueError
            else:
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

        if self.with_dcn:
            act_cfg_ = act_cfg.copy()
            # nn.Tanh has no 'inplace' argument
            if act_cfg_['type'] not in [
                    'Tanh', 'PReLU', 'Sigmoid', 'HSigmoid', 'Swish'
            ]:
                act_cfg_.setdefault('inplace', True)
            self.dcn = nn.Sequential(
                build_conv_layer(
                dcn_cfg,
                mid_channels,
                mid_channels,
                kernel_size=3,
                stride=1,
                padding=1,
                dilation=1,
                bias=False),
                build_norm_layer(norm_cfg, mid_channels)[1],
                build_activation_layer(act_cfg_)
            )
            self.linear_conv = ConvModule(
                in_channels=mid_channels*2,
                out_channels=out_channels,
                kernel_size=1,
                stride=1,
                padding=0,
                conv_cfg=conv_cfg,
                norm_cfg=norm_cfg,
                act_cfg=None)
        else:
            self.linear_conv = ConvModule(
                in_channels=mid_channels,
                out_channels=out_channels,
                kernel_size=1,
                stride=1,
                padding=0,
                conv_cfg=conv_cfg,
                norm_cfg=norm_cfg,
                act_cfg=None)
        if self.with_res_shortcut:
            self.down_conv = ConvModule(
                in_channels=out_channels * 2,
                out_channels=out_channels,
                kernel_size=1,
                stride=1,
                padding=0,
                conv_cfg=conv_cfg,
                norm_cfg=norm_cfg,
                act_cfg=act_cfg)

    def forward(self, x):

        def _inner_forward(x):
            out = x

            if self.with_expand_conv:
                out = self.expand_conv(out)

            if self.with_dcn:
                out1 = self.depthwise_conv(out)
                out2 = self.dcn(out)
                out = torch.cat((out1,out2), 1)
            else:
                out = self.depthwise_conv(out)

            if self.with_se:
                out = self.se(out)

            out = self.linear_conv(out)

            if self.with_res_shortcut:
                if self.cat_mode==True:
                    return self.down_conv(torch.cat((x, out), 1)) #
                else:
                    return x + out
            else:
                return out

        if self.with_cp and x.requires_grad:
            out = cp.checkpoint(_inner_forward, x)
        else:
            out = _inner_forward(x)

        return out
