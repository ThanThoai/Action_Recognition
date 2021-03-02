import os
import torch.nn.utils.prune as prune
# from model import C3D, ConvLSTM, 
from models.densenet import densenet88, densenet121
from dataset import RWF2000
import torch
from utils import AverageMeter
g_path = os.path.dirname(os.path.abspath(__file__))

def load_model(device):
    model = densenet88(num_classes=2,
                       sample_size=16,
                       sample_duration=224)

    state_dict = torch.load('weights/densenet_lean.pth')
    model.load_state_dict(state_dict)
    model.to(device)
    return model


def val(data_loader, model, criterion):
    model.eval()
    losses = AverageMeter()
    accuracies = AverageMeter()

    for _, (inputs, targets) in enumerate(data_loader):
        inputs = inputs
        targets = targets
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
        'Epoch: [{}]\t'
        'Loss(val): {loss.avg:.4f}\t'
        'Acc(val): {acc.avg:.3f}'.format(epoch, loss=losses, acc=accuracies)
    )

    val_log.log({'epoch': epoch, 'loss': losses.avg, 'acc': accuracies.avg})

    return losses.avg, accuracies.avg

def eval(model):
    
    val_data = RWF2000('/content/RWF_2000/frames/',
                     g_path + '/RWF-2000.json', 'validation',
                     spatial_transform, temporal_transform, target_transform, dataset)
    val_loader = DataLoader(val_data,
                            batch_size=32,
                            shuffle=False,
                            num_workers=4,
                            pin_memory=True)
    criterion = nn.CrossEntropyLoss()
    val_loss, val_acc = val(val_loader, model, criterion)
    print(val_loss)
    print(val_acc)
    
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


def prune_model(model, amount = 0.2, method = 'random_unstructured', type_param = 'weight'):
    for name, m in model.named_modules():
        if isinstance(m, torch.nn.Conv3d):
            if check_type(method) == 1:
                getattr(prune, method)(m, name = type_param, amount = amount)
            elif check_type(method) == -1:
                getattr(prune, method)(m, name = type_param, amount = amount, dim = 3, n = 2)
            else:
                getattr(prune, method)(m, name = type_param, amount = amount, dim = 3)
            prune.remove(m, name = type_param)
    return model
    


if __name__ == '__main__':
    LIST_METHOD_PRUNE = ['random_unstructured', 'l1_unstructured', 'random_structured', 'ln_structured']
    model = load_model('cpu')
    prune_model(model, method = LIST_METHOD_PRUNE[3])
    print(sparsity(model))
    eval(model)
            

