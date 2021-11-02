import chamferdist
import numpy as np
import torch
import torch.nn.functional as F


def calculate_loss(batch_size, constraint, flow, flow_pred, loss_opt, pc1, pc2, position1, loss_coeff):
    if 'all' in loss_opt:
        for loss in ["biomechanical", "rigidity", "chamfer"]:
            if loss not in loss_coeff.keys():
                loss_coeff[loss] = 1.0
    mse_loss = F.mse_loss(flow_pred.float(), flow.float())
    loss = torch.clone(mse_loss)
    bio_loss, rig_loss, cham_loss = torch.zeros_like(loss), torch.zeros_like(loss), torch.zeros_like(loss)
    if "biomechanical" in loss_opt or 'all' in loss_opt:
        for idx in range(batch_size):
            bio_loss += biomechanical_loss(constraint, flow, flow_pred, idx, pc1, coeff=loss_coeff["biomechanical"])
        loss += bio_loss
        bio_loss /= loss_coeff["biomechanical"]
    if "rigidity" in loss_opt or 'all' in loss_opt:
        rig_loss = rigidity_loss(flow, flow_pred, pc1, position1, coeff=loss_coeff["rigidity"])
        loss += rig_loss
        rig_loss /= loss_coeff["rigidity"]
    if "chamfer" in loss_opt or 'all' in loss_opt:
        cham_loss = chamfer_loss(flow, flow_pred, pc1, pc2, coeff=loss_coeff["chamfer"])
        loss += cham_loss
        cham_loss /= loss_coeff["chamfer"]
    return bio_loss, cham_loss, loss, mse_loss, rig_loss


chamfer = chamferdist.ChamferDistance()


def chamfer_loss(flow, flow_pred, pc1, pc2, coeff=1):
    predicted = pc1 + flow_pred

    loss = chamfer(predicted.type(torch.float), pc2.type(torch.float), bidirectional=True) * 1e-7
    return loss * coeff


def rigidity_loss(flow, flow_pred, pc1, position1, coeff=1):
    source_dist1 = torch.Tensor().cuda()
    source_dist2 = torch.Tensor().cuda()
    predict_dist1 = torch.Tensor().cuda()
    predict_dist2 = torch.Tensor().cuda()
    for idx in range(pc1.shape[0]):
        for p1 in position1:
            p1 = p1.type(torch.int).cuda()

            source_dist1 = torch.cat((source_dist1, torch.index_select(pc1[idx, ...], 1, p1[idx, :])[..., None]
                                      .expand(-1, -1, p1.size()[1]).reshape(3, -1).T), dim=0)

            source_dist2 = torch.cat((source_dist2, torch.index_select(pc1[idx, ...], 1, p1[idx, :])[None, ...]
                                      .expand(p1.size()[1], -1, -1).reshape(3, -1).T), dim=0)

            predict_dist1 = torch.cat(
                (predict_dist1, torch.index_select(pc1[idx, ...] + flow_pred[idx, ...], 1, p1[idx, :])[..., None]
                 .expand(-1, -1, p1.size()[1]).reshape(3, -1).T), dim=0)

            predict_dist2 = torch.cat(
                (predict_dist2, torch.index_select(pc1[idx, ...] + flow_pred[idx, ...], 1, p1[idx, :])[None, ...]
                 .expand(p1.size()[1], -1, -1).reshape(3, -1).T), dim=0)
    loss = torch.abs(torch.sqrt(F.mse_loss(source_dist1, source_dist2)) -
                     torch.sqrt(F.mse_loss(predict_dist1, predict_dist2)))
    return loss * coeff


def biomechanical_loss(constraint, flow, flow_pred, idx, pc1, coeff=1):
    source = pc1[idx, :, constraint[idx]]
    predicted = pc1[idx, :, constraint[idx]] + flow_pred[idx, :, constraint[idx]]
    loss = torch.tensor([0.0], device=flow.device, dtype=flow.dtype)
    for j in range(0, constraint.size(1) - 1, 2):
        loss += torch.abs(torch.linalg.norm(source[:, j] - source[:, j + 1]) -
                          torch.linalg.norm(predicted[:, j] - predicted[:, j + 1]))
    return loss[0] * coeff


def scene_flow_EPE_np(pred, labels, mask):
    error = np.sqrt(np.sum((pred - labels) ** 2, 2) + 1e-20)

    gtflow_len = np.sqrt(np.sum(labels * labels, 2) + 1e-20)  # B,N
    acc1 = np.sum(np.logical_or((error <= 0.05) * mask, (error / gtflow_len <= 0.05) * mask), axis=1)
    acc2 = np.sum(np.logical_or((error <= 0.1) * mask, (error / gtflow_len <= 0.1) * mask), axis=1)

    mask_sum = np.sum(mask, 1)
    acc1 = acc1[mask_sum > 0] / mask_sum[mask_sum > 0]
    acc1 = np.mean(acc1)
    acc2 = acc2[mask_sum > 0] / mask_sum[mask_sum > 0]
    acc2 = np.mean(acc2)

    EPE = np.sum(error * mask, 1)[mask_sum > 0] / mask_sum[mask_sum > 0]
    EPE = np.mean(EPE)
    return EPE, acc1, acc2
