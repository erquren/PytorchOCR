from __future__ import absolute_import
from __future__ import division
from __future__ import print_function

from torch import nn

__all__ = ["ResNet", "ResNet18_vd", "ResNet34_vd", "ResNet50_vd", "ResNet101_vd", "ResNet152_vd", "ResNet200_vd"]

from torchocr.networks.backbones.rec_mobilenet_v3 import ConvBNACT


class ConvBNACTNew(nn.Module):
    def __init__(self, in_channels, out_channels, kernel_size, stride=1, groups=1, act=None, name=None):
        super().__init__()
        self.pool = nn.AvgPool2d(kernel_size=stride, stride=stride, padding=0, ceil_mode=True)

        self.conv = nn.Conv2d(in_channels=in_channels, out_channels=out_channels, kernel_size=kernel_size, stride=1, padding=(kernel_size - 1) // 2,
                              groups=groups,
                              bias=False)
        self.bn = nn.BatchNorm2d(out_channels)
        if act is None:
            self.act = None
        else:
            self.act = nn.ReLU()

    def forward(self, x):
        x = self.pool(x)
        x = self.conv(x)
        x = self.bn(x)
        if self.act is not None:
            x = self.act(x)
        return x


class ShurtCut(nn.Module):
    def __init__(self, in_channels, out_channels, stride, if_first=False):
        super().__init__()
        if in_channels != out_channels or stride[0] != 1:
            if if_first:
                self.conv = ConvBNACT(in_channels=in_channels, out_channels=out_channels, kernel_size=1, stride=stride, padding=0, groups=1, act=None)
            else:
                self.conv = ConvBNACTNew(in_channels=in_channels, out_channels=out_channels, kernel_size=1, stride=stride, groups=1, act=None)
        elif if_first:
            self.conv = ConvBNACT(in_channels=in_channels, out_channels=out_channels, kernel_size=1, stride=stride, padding=0, groups=1, act=None)
        else:
            self.conv = None

    def forward(self, x):
        if self.conv is not None:
            x = self.conv(x)
        return x


class BasicBlock(nn.Module):
    def __init__(self, in_channels, out_channels, stride, if_first):
        super().__init__()
        self.conv0 = ConvBNACT(in_channels=in_channels, out_channels=out_channels, kernel_size=3, stride=stride, padding=1, groups=1, act='relu')
        self.conv1 = ConvBNACT(in_channels=out_channels, out_channels=out_channels, kernel_size=3, stride=1, padding=1, groups=1, act=None)
        self.shortcut = ShurtCut(in_channels=in_channels, out_channels=out_channels, stride=stride, if_first=if_first)
        self.relu = nn.ReLU()

    def forward(self, x):
        y = self.conv0(x)
        y = self.conv1(y)
        y = y + self.shortcut(x)
        return self.relu(y)


class BottleneckBlock(nn.Module):
    def __init__(self, in_channels, out_channels, stride, if_first):
        super().__init__()
        self.conv0 = ConvBNACT(in_channels=in_channels, out_channels=out_channels, kernel_size=1, stride=1, padding=0, groups=1, act='relu')
        self.conv1 = ConvBNACT(in_channels=out_channels, out_channels=out_channels, kernel_size=3, stride=stride, padding=1, groups=1, act='relu')
        self.conv2 = ConvBNACT(in_channels=out_channels, out_channels=out_channels * 4, kernel_size=1, stride=1, padding=1, groups=1, act=None)
        self.shortcut = ShurtCut(in_channels=in_channels, out_channels=out_channels * 4, stride=stride, if_first=if_first)
        self.relu = nn.ReLU()

    def forwart(self, x):
        y = self.conv0(x)
        y = self.conv1(y)
        y = self.conv2(y)
        y = y + self.shortcut(x)
        return self.relu(y)


class ResNet(nn.Module):
    def __init__(self, in_channels, layers, **kwargs):
        super().__init__()
        self.is_3x3 = True
        supported_layers = {
            18: {'depth': [2, 2, 2, 2], 'block_class': BasicBlock},
            34: {'depth': [3, 4, 6, 3], 'block_class': BasicBlock},
            50: {'depth': [3, 4, 6, 3], 'block_class': BottleneckBlock},
            101: {'depth': [3, 4, 23, 3], 'block_class': BottleneckBlock},
            152: {'depth': [3, 8, 36, 3], 'block_class': BottleneckBlock},
            200: {'depth': [3, 12, 48, 3], 'block_class': BottleneckBlock}
        }
        assert layers in supported_layers, "supported layers are {} but input layer is {}".format(supported_layers, layers)

        depth = supported_layers[layers]['depth']
        block_class = supported_layers[layers]['block_class']
        is_3x3 = self.is_3x3

        num_filters = [64, 128, 256, 512]
        if is_3x3 == False:
            self.conv1 = ConvBNACT(in_channels=in_channels, out_channels=64, kernel_size=7, stride=1, padding=3, act='relu')
        else:
            self.conv1 = nn.Sequential(
                ConvBNACT(in_channels=in_channels, out_channels=32, kernel_size=3, stride=1, padding=1, act='relu'),
                ConvBNACT(in_channels=32, out_channels=32, kernel_size=3, stride=1, act='relu', padding=1),
                ConvBNACT(in_channels=32, out_channels=64, kernel_size=3, stride=1, act='relu', padding=1)
            )

        self.pool1 = nn.MaxPool2d(kernel_size=3, stride=2, padding=1)

        self.stages = nn.ModuleList()
        in_ch = 64
        for block in range(len(depth)):
            block_list = []
            for i in range(depth[block]):
                if i == 0 and block != 0:
                    stride = (2, 1)
                else:
                    stride = (1, 1)
                block_list.append(block_class(in_channels=in_ch, out_channels=num_filters[block], stride=stride, if_first=block == i == 0))
                in_ch = num_filters[block]
            self.stages.append(nn.Sequential(*block_list))
        self.out_channels = in_ch
        self.out = nn.MaxPool2d(kernel_size=2, stride=2, padding=0)

    def forward(self, x):
        x = self.conv1(x)
        x = self.pool1(x)
        for stage in self.stages:
            x = stage(x)
        x = self.out(x)
        return x
