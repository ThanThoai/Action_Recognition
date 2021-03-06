import os
import torch.nn.utils.prune as prune
# from model import C3D, ConvLSTM, 
from models.densenet import densenet88, densenet121
from dataset import RWF2000
import torch
from utils import AverageMeter
from spatial_transforms import Compose, ToTensor, Normalize
from spatial_transforms import GroupRandomHorizontalFlip, GroupRandomScaleCenterCrop, GroupScaleCenterCrop
from temporal_transforms import CenterCrop, RandomCrop
from target_transforms import Label, Video
import torch
import torch.nn as nn
from torch.utils.data import DataLoader
import numpy as np
import torch_pruning as tp


g_path = os.path.dirname(os.path.abspath(__file__))
print(g_path)



def load_model(device):
    model = densenet88(num_classes=2,
                       sample_size=16,
                       sample_duration=224)

    state_dict = torch.load('/content/drive/MyDrive/RWF/pth/densenet_lean_fps16_rwf-20001_3_0.8450_0.366975.pth')
    model.load_state_dict(state_dict)
    model.to(device)
    return model

def calculate_accuracy(outputs, targets):
    batch_size = targets.size(0)

    _, pred = outputs.topk(1, 1, True)
    pred = pred.t()
    correct = pred.eq(targets.view(1, -1))
    n_correct_elems = correct.float().sum().item()

    return n_correct_elems / batch_size


def val(data_loader, model, criterion):
    model.eval()
    losses = AverageMeter()
    accuracies = AverageMeter()

    for _, (inputs, targets) in enumerate(data_loader):
        inputs = inputs.to('cuda')
        targets = targets.to('cuda')
        # print(np.shape(inputs))
        # targets_onehot = torch.nn.functional.one_hot(targets, num_classes = 2).type(torch.FloatTensor)
        # targets_onehot = targets_onehot.to(device)
        # no need to track grad in eval mode
        with torch.no_grad():
            outputs = model(inputs)
            loss = criterion(outputs, targets)
            acc = calculate_accuracy(outputs, targets)

        losses.update(loss.item(), inputs.size(0))
        accuracies.update(acc, inputs.size(0))

    print(
        'Loss(val): {loss.avg:.4f}\t'
        'Acc(val): {acc.avg:.3f}'.format(loss=losses, acc=accuracies)
    )

    # print(f'loss: {losses.avg}, acc: {accuracies.avg}')

    return losses.avg, accuracies.avg

def eval(model):
    crop_method = GroupRandomScaleCenterCrop(size=(224, 224))
    norm = Normalize([0.485, 0.456, 0.406], [0.229, 0.224, 0.225])
    spatial_transform = Compose(
        [crop_method,
            GroupRandomHorizontalFlip(),
            ToTensor(), norm])
    temporal_transform = RandomCrop(size=16, stride=1)
    target_transform = Label()
    val_data = RWF2000('/content/RWF_2000/frames/',
                     '/content/Action_Recognition' + '/RWF-2000.json', 'validation',
                     spatial_transform, temporal_transform, target_transform, 'rwf-2000')
    # print(len(val_data))
    val_loader = DataLoader(val_data,
                            batch_size=16,
                            shuffle=False,
                            num_workers=4,
                            pin_memory=True)
    criterion = nn.CrossEntropyLoss()
    val_loss, val_acc = val(val_loader, model, criterion)
    # print(val_loss)
    # print(val_acc)
    
def sparsity(model):
    # Return global model sparsity
    a, b = 0., 0.
    for p in model.parameters():
        a += p.numel()
        b += (p == 0).sum()
    return b / a

def check_type(method):
    if 'ln' in method:
        return -1
    if 'unstructured' in method:
        return 1
    return 0


def prune_model(model, prune_prob = 0.1):
    model.cpu()
    DG = tp.DependencyGraph().build_dependency( model, torch.randn(1, 3, 32, 32) )
    def prune_conv(conv, amount=0.2):
        strategy = tp.strategy.L1Strategy()
        pruning_index = strategy(conv.weight, amount=amount)
        plan = DG.get_pruning_plan(conv, tp.prune_conv, pruning_index)
        plan.exec()
    
    for _, m in model.named_modules():
        if isinstance(m, torch.nn.Conv2d):
            prune_conv(m, prune_prob)
    return model
    


if __name__ == '__main__':
    LIST_METHOD_PRUNE = ['random_unstructured', 'l1_unstructured', 'random_structured', 'ln_structured']
    amounts = [i * 0.05 for i in range(0, 18)]
    for methd in LIST_METHOD_PRUNE:
        print("Method: ", method)
        for amount in amounts:   
            model = load_model('cuda')
            prune_model(model, method = method, amount = amount)
            print(sparsity(model))
            eval(model)
            


