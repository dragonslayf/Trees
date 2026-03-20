#!/user/bin/env python
# -*- coding: utf-8 -*-
# @Time     : 2022/12/28 12:28
# @Author   : Bin Yang
# @File     : mulCBAM_layer.py

import mmcv
import torch
import torch.nn as nn
from mmcv.cnn import ConvModule, HSigmoid
from mmcv.runner import BaseModule
from mmcv.cnn import build_conv_layer
from .mulse_layer import BiSELayer, MSSELayer
from .CBAM_layer import channel_attention, spatial_attention


class BiSAMLayer(BaseModule):
    # 卷积核大小为7*7
    # def __init__(self, kernel_size=7):
    def __init__(self,
                 kernel_size=7,
                 conv_cfg=None,
                 act_cfg=None,
                 init_cfg=None):
        super(BiSAMLayer, self).__init__(init_cfg)

        # 为了保持卷积前后的特征图shape相同，卷积时需要padding
        padding = kernel_size // 2

        # 7*7卷积融合通道信息 [b,2,h,w]==>[b,1,h,w]
        # self.conv = nn.Conv2d(in_channels=2, out_channels=1, kernel_size=kernel_size,
        #                       padding=padding, bias=False)
        self.s_conv1 = build_conv_layer(
            conv_cfg,
            1,
            1,
            kernel_size=kernel_size,
            stride=1,
            padding=padding,
            dilation=1,
            bias=False)

        # self.s_conv2 = build_conv_layer(
        #     conv_cfg,
        #     expand_channels,
        #     1,
        #     kernel_size=1,
        #     stride=1,
        #     padding=0,
        #     dilation=1,
        #     bias=False)

        self.g_conv1 = build_conv_layer(
            conv_cfg,
            1,
            1,
            kernel_size=kernel_size,
            stride=1,
            padding=padding,
            dilation=1,
            bias=False)

        # self.g_conv2 = build_conv_layer(
        #     conv_cfg,
        #     expand_channels,
        #     1,
        #     kernel_size=1,
        #     stride=1,
        #     padding=0,
        #     dilation=1,
        #     bias=False)

        # sigmoid函数
        self.hsigmoid = HSigmoid()
        # self.relu = nn.ReLU6()

    # 前向传播
    def forward(self, inputs):
        # 在通道维度上最大池化 [b,1,h,w]  keepdim保留原有深度
        # 返回值是在某维度的最大值和对应的索引
        x_maxpool, _ = torch.max(inputs, dim=1, keepdim=True)

        # 在通道维度上平均池化 [b,1,h,w]
        x_avgpool = torch.mean(inputs, dim=1, keepdim=True)
        # 池化后的结果在通道维度上堆叠 [b,2,h,w]
        # x = torch.cat([x_maxpool, x_avgpool], dim=1)

        # 卷积融合通道信息 [b,2,h,w]==>[b,1,h,w]
        # x = self.conv(x)
        x1 = self.s_conv1(x_maxpool)
        x2 = self.g_conv1(x_avgpool)
        # x1 = self.relu(x1)
        # x2 = self.relu(x2)

        # x1 = self.s_conv2(x1)
        # x2 = self.g_conv2(x2)
        x1 = self.hsigmoid(x1)
        x2 = self.hsigmoid(x2)

        # 空间权重归一化
        # x = self.hsigmoid(x)

        # 输入特征图和空间权重相乘
        outputs = (inputs * x1) * x2 + inputs

        return outputs


class MSSAMLayer(BaseModule):
    # 卷积核大小为7*7
    # def __init__(self, kernel_size=7):
    def __init__(self,
                 kernel_size=7,
                 conv_cfg=None,
                 act_cfg=None,
                 init_cfg=None):
        super(MSSAMLayer, self).__init__(init_cfg)

        # 为了保持卷积前后的特征图shape相同，卷积时需要padding
        padding = kernel_size // 2

        # 7*7卷积融合通道信息 [b,2,h,w]==>[b,1,h,w]
        # self.conv = nn.Conv2d(in_channels=2, out_channels=1, kernel_size=kernel_size,
        #                       padding=padding, bias=False)
        self.s_conv1 = build_conv_layer(
            conv_cfg,
            1,
            1,
            kernel_size=kernel_size,
            stride=1,
            padding=padding,
            dilation=1,
            bias=False)

        self.s_conv2 = build_conv_layer(
            conv_cfg,
            1,
            1,
            kernel_size=kernel_size,
            stride=1,
            padding=padding,
            dilation=1,
            bias=False)

        self.s_conv3 = build_conv_layer(
            conv_cfg,
            1,
            1,
            kernel_size=kernel_size,
            stride=1,
            padding=padding,
            dilation=1,
            bias=False)


        self.g_conv1 = build_conv_layer(
            conv_cfg,
            1,
            1,
            kernel_size=kernel_size,
            stride=1,
            padding=padding,
            dilation=1,
            bias=False)

        self.g_conv2 = build_conv_layer(
            conv_cfg,
            1,
            1,
            kernel_size=kernel_size,
            stride=1,
            padding=padding,
            dilation=1,
            bias=False)

        self.g_conv3 = build_conv_layer(
            conv_cfg,
            1,
            1,
            kernel_size=kernel_size,
            stride=1,
            padding=padding,
            dilation=1,
            bias=False)

        # sigmoid函数
        self.Hsigmoid = HSigmoid()
        self.relu = nn.ReLU6()

    # 前向传播
    def forward(self, inputs):
        # 在通道维度上最大池化 [b,1,h,w]  keepdim保留原有深度
        # 返回值是在某维度的最大值和对应的索引
        x_maxpool, _ = torch.max(inputs, dim=1, keepdim=True)

        # 在通道维度上平均池化 [b,1,h,w]
        x_avgpool = torch.mean(inputs, dim=1, keepdim=True)
        # 池化后的结果在通道维度上堆叠 [b,2,h,w]
        # x = torch.cat([x_maxpool, x_avgpool], dim=1)

        # 卷积融合通道信息 [b,2,h,w]==>[b,1,h,w]
        # x = self.conv(x)
        x1 = self.s_conv1(x_maxpool)
        x2 = self.g_conv1(x_avgpool)
        out = (self.Hsigmoid(x1) * inputs) * self.Hsigmoid(x2)
        x1 = self.relu(x1)
        x2 = self.relu(x2)

        x1 = self.s_conv2(x1)
        x2 = self.g_conv2(x2)
        out = (self.Hsigmoid(x1) * out) * self.Hsigmoid(x2)
        x1 = self.relu(x1)
        x2 = self.relu(x2)

        x1 = self.s_conv3(x1)
        x2 = self.g_conv3(x2)
        out = (self.Hsigmoid(x1) * out) * self.Hsigmoid(x2)

        # 空间权重归一化
        # x = self.hsigmoid(x)

        # 输入特征图和空间权重相乘
        outputs = out + inputs

        return outputs

# （4）CBAM注意力机制
class BBCBAM(BaseModule):
    # Multi-dimensional Convolutional Block Attention Module
    # 初始化，in_channel和ratio=4代表通道注意力机制的输入通道数和第一个全连接下降的通道数
    # kernel_size代表空间注意力机制的卷积核大小
    # def __init__(self, in_channel, ratio=5, kernel_size=7):
    def __init__(self,
                 channels,
                 ratio=4,
                 kernel_size=7,
                 conv_cfg=None,
                 act_cfg=(dict(type='ReLU'), dict(type='HSigmoid')),
                 init_cfg=None):
        super(BBCBAM, self).__init__(init_cfg)
        # 实例化通道注意力机制
        self.channel_attention = BiSELayer(channels=channels, ratio=ratio, conv_cfg=conv_cfg, act_cfg=act_cfg)
        # 实例化空间注意力机制
        self.spatial_attention = BiSAMLayer(kernel_size=kernel_size, conv_cfg=conv_cfg, act_cfg=act_cfg[0])

    # 前向传播
    def forward(self, inputs):
        # 先将输入图像经过通道注意力机制
        x = self.channel_attention(inputs)

        # 然后经过空间注意力机制
        x = self.spatial_attention(x)

        return x

# （4）CBAM注意力机制
class BMCBAM(BaseModule):
    # Multi-dimensional Convolutional Block Attention Module
    # 初始化，in_channel和ratio=4代表通道注意力机制的输入通道数和第一个全连接下降的通道数
    # kernel_size代表空间注意力机制的卷积核大小
    # def __init__(self, in_channel, ratio=5, kernel_size=7):
    def __init__(self,
                 channels,
                 ratio=4,
                 kernel_size=7,
                 conv_cfg=None,
                 act_cfg=(dict(type='ReLU'), dict(type='HSigmoid')),
                 init_cfg=None):
        super(BMCBAM, self).__init__(init_cfg)
        # 实例化通道注意力机制
        self.channel_attention = BiSELayer(channels=channels, ratio=ratio, conv_cfg=conv_cfg, act_cfg=act_cfg)
        # 实例化空间注意力机制
        self.spatial_attention = MSSAMLayer(kernel_size=kernel_size, conv_cfg=conv_cfg, act_cfg=act_cfg[0])

    # 前向传播
    def forward(self, inputs):
        # 先将输入图像经过通道注意力机制
        x = self.channel_attention(inputs)

        # 然后经过空间注意力机制
        x = self.spatial_attention(x)

        return x

# （4）CBAM注意力机制
class MMCBAM(BaseModule):
    # Multi-dimensional Convolutional Block Attention Module
    # 初始化，in_channel和ratio=4代表通道注意力机制的输入通道数和第一个全连接下降的通道数
    # kernel_size代表空间注意力机制的卷积核大小
    # def __init__(self, in_channel, ratio=5, kernel_size=7):
    def __init__(self,
                 channels,
                 ratio=4,
                 kernel_size=7,
                 conv_cfg=None,
                 act_cfg=(dict(type='ReLU'), dict(type='HSigmoid')),
                 init_cfg=None):
        super(MMCBAM, self).__init__(init_cfg)
        # 实例化通道注意力机制
        self.channel_attention = MSSELayer(channels=channels, ratio=ratio, conv_cfg=conv_cfg, act_cfg=act_cfg)
        # 实例化空间注意力机制
        self.spatial_attention = MSSAMLayer(kernel_size=kernel_size, conv_cfg=conv_cfg, act_cfg=act_cfg)

    # 前向传播
    def forward(self, inputs):
        # 先将输入图像经过通道注意力机制
        x = self.channel_attention(inputs)

        # 然后经过空间注意力机制
        x = self.spatial_attention(x)

        return x

# （4）CBAM注意力机制
class MBCBAM(BaseModule):
    # Multi-dimensional Convolutional Block Attention Module
    # 初始化，in_channel和ratio=4代表通道注意力机制的输入通道数和第一个全连接下降的通道数
    # kernel_size代表空间注意力机制的卷积核大小
    # def __init__(self, in_channel, ratio=5, kernel_size=7):
    def __init__(self,
                 channels,
                 ratio=4,
                 kernel_size=7,
                 conv_cfg=None,
                 act_cfg=(dict(type='ReLU'), dict(type='HSigmoid')),
                 init_cfg=None):
        super(MBCBAM, self).__init__(init_cfg)
        # 实例化通道注意力机制
        self.channel_attention = MSSELayer(channels=channels, ratio=ratio, conv_cfg=conv_cfg, act_cfg=act_cfg)
        # 实例化空间注意力机制
        self.spatial_attention = BiSAMLayer(kernel_size=kernel_size, conv_cfg=conv_cfg, act_cfg=act_cfg)

    # 前向传播
    def forward(self, inputs):
        # 先将输入图像经过通道注意力机制
        x = self.channel_attention(inputs)

        # 然后经过空间注意力机制
        x = self.spatial_attention(x)

        return x