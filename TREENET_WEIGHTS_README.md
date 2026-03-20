# 关于 20250416_001154_epoch36_latest.pth 与 TreeNet / TREEFPN

## 为什么报 “model and loaded state dict do not match”？

该权重是用**训练时的真实 TreeNet、TREEFPN** 得到的，和当前项目里的**占位实现**结构不同，所以不能直接加载。

- **权重里的 backbone** 结构大致为：
  - `backbone.layer0`：普通 conv+bn（3 通道输入）
  - `backbone.layer1`～`layer11`：每层含 `expand_conv`、`depthwise_conv`、`se`、`dcn`、`linear_conv`、`down_conv` 等（轻量/移动端风格）
  - `backbone.layer12`：末尾 conv+bn
- **权重里的 neck** 结构大致为：
  - `neck.extra_downsamples`、`neck.treefpn_convs`、`neck.fpn_stages`（含 `gp_64_4`、`sum_44_4` 等）、`neck.lateral_convs`

而 `mmdet_custom_models.py` 里的是**占位实现**（如 `backbone.stages.0/1/2/3`、简单 FPN），和上面这些 key **对不上**，因此会出现 “unexpected key / missing key”。

## 正确用法（推荐）

必须使用**训练该权重时用的那一套 TreeNet、TREEFPN 代码**，才能正确加载并推理：

1. 找到训练 20250416_001154_epoch36_latest.pth 时用的代码库（例如当时用的 mmdet 扩展或私有仓库）。
2. 把其中的 **TreeNet**（backbone）和 **TREEFPN**（neck）实现拷到本项目中，或通过 `custom_imports` 指向该实现所在模块。
3. 确保 config 里 `backbone.type='TreeNet'`、`neck.type='TREEFPN'` 能解析到**这一套实现**，再运行推理。

这样模型结构和权重里的 key 一致，就不会再报 state_dict 不匹配。

## 若用 strict=False 强行加载

也可以用 `load_checkpoint(..., strict=False)` 强行加载权重：  
**未匹配上的参数（包括整个 backbone 和 neck）会保持随机初始化**，推理结果没有意义，仅适合做调试或确认其他部分能跑通。

结论：要得到正确推理结果，必须使用与训练时一致的 TreeNet / TREEFPN 实现，不能依赖当前占位实现。
