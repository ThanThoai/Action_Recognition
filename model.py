import torch
import torch.nn as nn

import models.densenet as dn
from models.c3d import C3D
from models.densenet import densenet88, densenet121
from models.convlstm import ConvLSTM
import os

g_path = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
print(g_path)

def C3D(config):
    device = config.device
    model = C3D(num_classes=2).to(device)

    state_dict = torch.load('weights/C3D_Kinetics.pth')
    # for state in state_dict.keys():
    #     print(state)
    # print("-------------------")
    # for param in model.named_modules():
    #     print(param)
    model.load_state_dict(state_dict, strict = False)
    params = model.parameters()

    return model, params


def ConvLSTM(config):
    device = config.device
    model = ConvLSTM(256, device).to(device)
    for name, param in model.named_parameters():
        if 'conv_net' in name:
            param.requires_grad = False
    params = model.parameters()

    return model, params


def densenet(config):
    device = config.device
    ft_begin_idx = config.ft_begin_idx
    sample_size = config.sample_size[0]
    sample_duration = config.sample_duration

    model = densenet121(num_classes=2,
                        sample_size=sample_size,
                        sample_duration=sample_duration).to(device)

    state_dict = torch.load('weights/DenseNet_Kinetics.pth')
    model.load_state_dict(state_dict)

    params = dn.get_fine_tuning_params(model, ft_begin_idx)

    return model, params


def densenet_lean(config):
    device = config.device
    ft_begin_idx = config.ft_begin_idx
    sample_size = config.sample_size[0]
    sample_duration = config.sample_duration

    model = densenet88(num_classes=2,
                       sample_size=sample_size,
                       sample_duration=sample_duration).to(device)

    state_dict = torch.load('weights/DenseNetLean_Kinetics.pth')
    model.load_state_dict(state_dict)

    params = dn.get_fine_tuning_params(model, ft_begin_idx)

    return model, params
