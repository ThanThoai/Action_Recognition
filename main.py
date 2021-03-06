import os

import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import sys
from epoch import train, val, test
from model import C3D, ConvLSTM, densenet, densenet_lean
from dataset import RWF2000
from config import Config
import numpy as np
from spatial_transforms import Compose, ToTensor, Normalize
from spatial_transforms import *
from temporal_transforms import CenterCrop, RandomCrop
from target_transforms import Label, Video

from utils import Log
g_path = os.path.dirname(os.path.abspath(__file__))
import torch_pruning as tp
print('main g_path:', g_path)
# g_path = "."

def prune_model(model, prune_prob = 0.1):
    model.cpu()
    DG = tp.DependencyGraph().build_dependency(model, torch.randn(1, 3, 32, 224, 224))
    def prune_conv(conv, amount=0.2):
        strategy = tp.strategy.L1Strategy()
        pruning_index = strategy(conv.weight, amount=amount)
        plan = DG.get_pruning_plan(conv, tp.prune_conv, pruning_index)
        plan.exec()
    
    for _, m in model.named_modules():
        if isinstance(m, torch.nn.Conv3d):
            prune_conv(m, prune_prob)
    return model

def main(config):
    if config.model == 'c3d':
        model, params = C3D(config)
    elif config.model == 'convlstm':
        model, params = ConvLSTM(config)
    elif config.model == 'densenet':
        model, params = densenet(config)
    elif config.model == 'densenet_lean':
        model, params = densenet_lean(config)
    elif config.model == 'resnext':
        model, params = resnext(config)
    else:
        model, params = densenet_lean(config)
    
    dataset = config.dataset
    sample_size = config.sample_size
    stride = config.stride
    sample_duration = config.sample_duration

    cv = config.num_cv

    # crop_method = GroupRandomScaleCenterCrop(size=sample_size)
    crop_method = MultiScaleRandomCrop(config.scales, config.sample_size[0])
    # norm = Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])

    norm = Normalize([114.7748, 107.7354, 99.475], [1, 1, 1])
    # spatial_transform = Compose(
    #     [crop_method,
    #      GroupRandomHorizontalFlip(),
    #      ToTensor(1), norm])
    spatial_transform = Compose(
        [
            RandomHorizontalFlip(),
            crop_method,
            ToTensor(config.norm_value),
            norm
        ]
    )
    # temporal_transform = RandomCrop(size=sample_duration, stride=stride)
    temporal_transform = TemporalRandomCrop(config.sample_duration, config.downsample)
    target_transform = Label()

    train_batch = config.train_batch
    train_data = RWF2000('/content/RWF_2000/frames/',
                       g_path + '/RWF-2000.json', 'training',
                       spatial_transform, temporal_transform, target_transform, dataset)
    train_loader = DataLoader(train_data,
                              batch_size=train_batch,
                              shuffle=True,
                              num_workers=4,
                              pin_memory=True)

    crop_method = GroupScaleCenterCrop(size=sample_size)
    norm = Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    spatial_transform = Compose([crop_method, ToTensor(), norm])
    temporal_transform = CenterCrop(size=sample_duration, stride=stride)
    target_transform = Label()

    val_batch = config.val_batch

    val_data = RWF2000('/content/RWF_2000/frames/',
                     g_path + '/RWF-2000.json', 'validation',
                     spatial_transform, temporal_transform, target_transform, dataset)
    val_loader = DataLoader(val_data,
                            batch_size=val_batch,
                            shuffle=False,
                            num_workers=4,
                            pin_memory=True)

    if not os.path.exists('{}/pth'.format(config.output)):
        os.mkdir('{}/pth'.format(config.output))
    if not os.path.exists('{}/log'.format(config.output)):
        os.mkdir('{}/log'.format(config.output))

    batch_log = Log(
        '{}/log/{}_fps{}_{}_batch{}.log'.format(
            config.output,
            config.model,
            sample_duration,
            dataset,
            cv,
        ), ['epoch', 'batch', 'iter', 'loss', 'acc', 'lr'])
    epoch_log = Log(
        '{}/log/{}_fps{}_{}_epoch{}.log'.format(config.output, config.model, sample_duration,
                                               dataset, cv),
        ['epoch', 'loss', 'acc', 'lr'])
    val_log = Log(
        '{}/log/{}_fps{}_{}_val{}.log'.format(config.output, config.model, sample_duration,
                                             dataset, cv),
        ['epoch', 'loss', 'acc'])

    criterion = nn.CrossEntropyLoss().to(device)
    # criterion = nn.BCELoss().to(device)

    learning_rate = config.learning_rate
    momentum = config.momentum
    weight_decay = config.weight_decay

    optimizer = torch.optim.SGD(params=params,
                                lr=learning_rate,
                                momentum=momentum,
                                weight_decay=weight_decay,dampening=False,nesterov=False)

    # optimizer = torch.optim.Adam(params=params, lr = learning_rate, weight_decay= weight_decay)

    scheduler = torch.optim.lr_scheduler.ReduceLROnPlateau(optimizer,
                                                           verbose=True,
                                                           factor=config.factor,
                                                           min_lr=config.min_lr)

    acc_baseline = config.acc_baseline
    loss_baseline = 1
    
    for p in range(1, config.num_prune):
        if p > 0:
            model = torch.load('{}/pth/prune_{}.pth'.format(config.output, p - 1))
        print(f"Prune {p}/{config.num_prune}")
        params = sum([np.prod(p.size()) for p in model.parameters()])
        print("Number of Parameters: %.1fM"%(params/1e6))
        model = prune_model(model)
        params = sum([np.prod(p.size()) for p in model.parameters()])
        print("Number of Parameters: %.1fM"%(params/1e6))
        model.to(config.device)
        acc_baseline = 0
        for i in range(5):
            train(i, train_loader, model, criterion, optimizer, device, batch_log,
                  epoch_log)
            val_loss, val_acc = val(i, val_loader, model, criterion, device,
                                    val_log)
            scheduler.step(val_loss)
            if val_acc > acc_baseline or (val_acc >= acc_baseline and
                                        val_loss < loss_baseline):
                # torch.save(
                    # model.state_dict(),
                    # '{}/pth/prune_{}_{}_fps{}_{}{}_{}_{:.4f}_{:.6f}.pth'.format(
                    #     config.output, p, config.model, sample_duration, dataset, cv, i, val_acc,
                    #     val_loss))
                torch.save(model, '{}/pth/prune_{}.pth'.format(config.output, p))
                # acc_baseline = val_acc
                # loss_baseline = val_loss


if __name__ == '__main__':
    device = torch.device('cuda:0' if torch.cuda.is_available() else 'cpu')
    config = Config(
        'resnext', 
        'rwf-2000',
        device=device,
        num_epoch=10,
        acc_baseline=0.0,
        ft_begin_idx=0,
    )

    config.dataset = 'rwf-2000'
    config.train_batch = 8
    config.val_batch = 8
    config.learning_rate = 1e-2
    config.num_cv = 1
    config.output = sys.argv[1]
    main(config)
    
    
    
