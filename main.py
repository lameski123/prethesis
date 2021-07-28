#!/usr/bin/env python
# -*- coding: utf-8 -*-


from __future__ import print_function
import os
import gc
import argparse
import torch
import torch.nn as nn
import torch.nn.functional as F
import torch.optim as optim
from torch.optim.lr_scheduler import MultiStepLR, StepLR
from data import ModelNet40, SceneflowDataset
from model import FlowNet3D
import numpy as np
from torch.utils.data import DataLoader
# from tensorboardX import SummaryWriter
from tqdm import tqdm
import sklearn
import chamferdist
import wandb
import itk
import pandas as pd
from sklearn.model_selection import KFold, StratifiedKFold
from typing import Iterator, Optional, Sequence, List, TypeVar, Generic, Sized

T_co = TypeVar('T_co', covariant=True)



class dotdict(dict):
    """dot.notation access to dictionary attributes"""
    __getattr__ = dict.get
    __setattr__ = dict.__setitem__
    __delattr__ = dict.__delitem__

mydict = {'val':'it works'}
nested_dict = {'val':'nested works too'}
mydict = dotdict(mydict)
mydict.val

class IOStream:
    def __init__(self, path):
        self.f = open(path, 'a')

    def cprint(self, text):
        print(text)
        self.f.write(text + '\n')
        self.f.flush()

    def close(self):
        self.f.close()


def _init_(exp_name):
    if not os.path.exists('checkpoints'):
        os.makedirs('checkpoints')
    if not os.path.exists('checkpoints/' + exp_name):
        os.makedirs('checkpoints/' + exp_name)
    if not os.path.exists('checkpoints/' + exp_name + '/' + 'models'):
        os.makedirs('checkpoints/' + exp_name + '/' + 'models')
    os.system('cp main.py checkpoints' + '/' + exp_name + '/' + 'main.py.backup')
    os.system('cp model.py checkpoints' + '/' + exp_name + '/' + 'model.py.backup')
    os.system('cp data.py checkpoints' + '/' + exp_name + '/' + 'data.py.backup')

def weights_init(m):
    classname=m.__class__.__name__
    if classname.find('Conv2d') != -1:
        nn.init.kaiming_normal_(m.weight.data)
    if classname.find('Conv1d') != -1:
        nn.init.kaiming_normal_(m.weight.data)

def scene_flow_EPE_np(pred, labels, mask):
    error = np.sqrt(np.sum((pred - labels)**2, 2) + 1e-20)

    gtflow_len = np.sqrt(np.sum(labels*labels, 2) + 1e-20) # B,N
    acc1 = np.sum(np.logical_or((error <= 0.05)*mask, (error/gtflow_len <= 0.05)*mask), axis=1)
    acc2 = np.sum(np.logical_or((error <= 0.1)*mask, (error/gtflow_len <= 0.1)*mask), axis=1)

    mask_sum = np.sum(mask, 1)
    acc1 = acc1[mask_sum > 0] / mask_sum[mask_sum > 0]
    acc1 = np.mean(acc1)
    acc2 = acc2[mask_sum > 0] / mask_sum[mask_sum > 0]
    acc2 = np.mean(acc2)

    EPE = np.sum(error * mask, 1)[mask_sum > 0] / mask_sum[mask_sum > 0]
    EPE = np.mean(EPE)
    return EPE, acc1, acc2

def test_one_epoch(args, net, test_loader):
    net.eval()

    total_loss = 0
    total_epe = 0
    total_acc3d = 0
    total_acc3d_2 = 0
    num_examples = 0
    chamfer = chamferdist.ChamferDistance()


    for i, data in tqdm(enumerate(test_loader), total = len(test_loader)):
        pc1, pc2, color1, color2, flow, mask1, position1, position2 = data
        ind1 = position1.type(torch.int).cuda()
        ind2 = position2.type(torch.int).cuda()
        pc1_surf = torch.zeros_like(pc1).type(torch.int).cuda()
        pc2_surf = torch.zeros_like(pc2).type(torch.int).cuda()
        pc1 = pc1.cuda().transpose(2, 1).contiguous()
        pc2 = pc2.cuda().transpose(2, 1).contiguous()
        color1 = color1.cuda().transpose(2, 1).contiguous().float()
        color2 = color2.cuda().transpose(2, 1).contiguous().float()
        flow = flow.cuda().contiguous()
        mask1 = mask1.cuda().float()

        for i in range(pc1.shape[0]):
            pc1_surf[i, :] = torch.index_select(pc1[i, :], 1, ind1[i, :]).transpose(1, 0).cuda()
            pc2_surf[i, :] = torch.index_select(pc2[i, :], 1, ind2[i, :]).transpose(1, 0).cuda()

        batch_size = pc1.size(0)
        num_examples += batch_size
        flow_pred = net(pc1, pc2, color1, color2).permute(0, 2, 1)
        loss = torch.mean(mask1 * torch.sum((flow_pred - flow) ** 2, -1) / 2.0) + \
                5 * chamfer(pc1_surf.type(torch.float), pc2_surf.type(torch.float), bidirectional=True)

        epe_3d, acc_3d, acc_3d_2 = scene_flow_EPE_np(flow_pred.detach().cpu().numpy(), flow.detach().cpu().numpy(),
                                                     mask1.detach().cpu().numpy())
        total_epe += epe_3d * batch_size
        # total_acc3d += acc_3d * batch_size
        # total_acc3d_2 += acc_3d_2 * batch_size
        # print('batch EPE 3D: %f\tACC 3D: %f\10    tACC 3D 2: %f' % (epe_3d, acc_3d, acc_3d_2))

        total_loss += loss.item() * batch_size
        

    return total_loss*1.0/num_examples, total_epe*1.0/num_examples


def train_one_epoch(args, net, train_loader, opt):
    net.train()
    num_examples = 0
    total_loss = 0
    chamfer = chamferdist.ChamferDistance()
    for i, data in tqdm(enumerate(train_loader), total = len(train_loader)):

        pc1, pc2, color1, color2, flow, mask1, position1, position2= data


        ind1 = position1.type(torch.int).cuda()
        ind2 = position2.type(torch.int).cuda()
        pc1 = pc1.cuda().transpose(2, 1).contiguous()
        pc2 = pc2.cuda().transpose(2, 1).contiguous()
        color1 = color1.cuda().transpose(2, 1).contiguous().float()
        color2 = color2.cuda().transpose(2, 1).contiguous().float()
        flow = flow.cuda().transpose(2, 1).contiguous()
        mask1 = mask1.cuda().float()
        pc1_surf = torch.zeros_like(pc1).type(torch.int).cuda()
        pc2_surf = torch.zeros_like(pc2).type(torch.int).cuda()
        for i in range(pc1.shape[0]):
            pc1_surf[i,:] = torch.index_select(pc1[i,:], 1, ind1[i, :]).cuda()#.transpose(1, 0).cuda()
            pc2_surf[i,:] = torch.index_select(pc2[i,:], 1, ind2[i, :]).cuda()#.transpose(1, 0).cuda()

        batch_size = pc1.size(0)
        opt.zero_grad()
        num_examples += batch_size
        flow_pred = net(pc1, pc2, color1, color2)

        loss = torch.mean(mask1 * torch.sum((flow_pred - flow) ** 2, 1) / 2.0) + \
               5 * chamfer(pc1_surf.type(torch.float).transpose(2,1),
                           pc2_surf.type(torch.float).transpose(2,1),
                           bidirectional=True)

        loss.backward()

        opt.step()

        total_loss += loss.item() * batch_size

        # if (i+1) % 100 == 0:
        #     print("batch: %d, mean loss: %f" % (i, total_loss / 100 / batch_size))
        #     total_loss = 0
    return total_loss*1.0/num_examples


def test(args, net, test_loader, boardio, textio):

    test_loss, epe= test_one_epoch(args, net, test_loader)

    textio.cprint('==FINAL TEST==')
    textio.cprint('mean test loss: %f\tEPE 3D: %f'%(test_loss, epe))


def train(args, net, train_loader, test_loader, boardio, textio):
    if args.use_sgd:
        print("Use SGD")
        opt = optim.SGD(net.parameters(), lr=args.lr * 100, momentum=args.momentum, weight_decay=1e-4)
    else:
        print("Use Adam")
        opt = optim.Adam(net.parameters(), lr=args.lr, weight_decay=1e-4)
    # scheduler = MultiStepLR(opt, milestones=[75, 150, 200], gamma=0.1)
    scheduler = StepLR(opt, 5, gamma = 0.7)

    best_test_loss = np.inf
    for epoch in range(args.epochs):
        textio.cprint('==epoch: %d, learning rate: %f=='%(epoch, opt.param_groups[0]['lr']))
        train_loss = train_one_epoch(args, net, train_loader, opt)
        textio.cprint('mean train EPE loss: %f'%train_loss)

        test_loss, epe= test_one_epoch(args, net, test_loader)
        textio.cprint('mean test loss: %f\tEPE 3D: %f'%(test_loss, epe))
        if best_test_loss >= test_loss:
            best_test_loss = test_loss
            textio.cprint('best test loss till now: %f'%test_loss)
            if torch.cuda.device_count() > 1:
                torch.save(net.module.state_dict(), 'checkpoints/%s/models/model.best.t7' % args.exp_name)
            else:
                torch.save(net.state_dict(), 'checkpoints/%s/models/model.best.t7' % args.exp_name)

        scheduler.step()
        wandb.log({"Train loss": train_loss})
        wandb.log({"Val loss": test_loss})
        # print(scheduler.get_last_lr())
        args.lr = scheduler.get_last_lr()[0]
        # if torch.cuda.device_count() > 1:
        #     torch.save(net.module.state_dict(), 'checkpoints/%s/models/model.%d.t7' % (args.exp_name, epoch))
        # else:
        #     torch.save(net.state_dict(), 'checkpoints/%s/models/model.%d.t7' % (args.exp_name, epoch))
        # gc.collect()
        # return train_loss, test_loss

if __name__ == '__main__':
    # main()
    args = {"exp_name":"flownet3d","emb_dims":512, "num_points":4096,
            "lr":0.001, "momentum":0.9,"seed":100, "dropout":0.5,
            "batch_size":4, "test_batch_size":4, "epochs":25,
            "use_sgd":False, "eval":False, "cycle":False,
            "gaussian_noise":False}
    args = dotdict(args)
    print(args.use_sgd)
    torch.backends.cudnn.deterministic = True
    torch.manual_seed(100)
    torch.cuda.manual_seed_all(100)
    np.random.seed(100)

    # boardio = SummaryWriter(log_dir='checkpoints/' + args.exp_name)
    boardio = []
    _init_("flownet3d")

    textio = IOStream('checkpoints/' + "flownet3d" + '/run.log')
    textio.cprint(str(args))

    dataset = SceneflowDataset(npoints=4096)


    kf = KFold(n_splits=5, shuffle=True, random_state=5)

    net = FlowNet3D(args).cuda()
    net.apply(weights_init)
    # net.load_state_dict(torch.load("./checkpoints/flownet3d/models/model.best.t7"))
    for fold, (tr_idx, val_idx) in enumerate(kf.split(dataset)):
        wandb.init(config=args)
        print("FOLD: ", fold)
        train_subsampler = torch.utils.data.SubsetRandomSampler(tr_idx)
        test_subsampler = torch.utils.data.SubsetRandomSampler(val_idx)

        train_loader = DataLoader(dataset,
            batch_size=args.batch_size, drop_last=True, sampler=train_subsampler)
        test_loader = DataLoader(
            dataset,
            batch_size=args.batch_size,  drop_last=False, sampler=test_subsampler)

        if torch.cuda.device_count() > 1:
            net = nn.DataParallel(net)
            print("Let's use", torch.cuda.device_count(), "GPUs!")
        # wandb.watch(net, log_freq=100)
        train(args, net, train_loader, test_loader, boardio, textio)

        #visualisation of each epoch:
        pc1, pc2, color1, color2, flow, mask1, position1, position2 = next(iter(test_loader))
        pc1 = pc1.cuda().transpose(2, 1).contiguous()
        pc2 = pc2.cuda().transpose(2, 1).contiguous()
        color1 = color1.cuda().transpose(2, 1).contiguous().float()
        color2 = color2.cuda().transpose(2, 1).contiguous().float()
        flow = flow.cuda().transpose(2, 1).contiguous()
        mask1 = mask1.cuda().float()
        flow_pred = net(pc1,pc2,color1, color2)
        pc1 = pc1.transpose(1,2).detach().cpu().numpy()[0,:,:].squeeze()
        pc2 = pc2.transpose(1,2).detach().cpu().numpy()[0,:,:].squeeze()
        flow = flow.transpose(1,2).detach().cpu().numpy()[0,:,:].squeeze()
        flow_min = flow.min()
        flow_max = flow.max()
        flow_pred = flow_pred.transpose(1,2).detach().cpu().numpy()[0,:,:].squeeze()
        wandb.log({
            "source": wandb.Object3D(
                {
                    "type": "lidar/beta",
                    "points": pc1[:,:3]
                }
            )})
        wandb.log({
            "registered": wandb.Object3D(
                {
                    "type": "lidar/beta",
                    "points": pc1[:,:3] + flow_pred
                }
            )})
        wandb.log({
            "target": wandb.Object3D(
                {
                    "type": "lidar/beta",
                    "points": pc2[:,:3]
                }
            )})
        wandb.log({
            "sanity target check": wandb.Object3D(
                {
                    "type": "lidar/beta",
                    "points": pc1[:,:3] + flow
                }
            )})
        wandb.join()


