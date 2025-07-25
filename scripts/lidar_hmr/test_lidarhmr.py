import faulthandler
faulthandler.enable()
import torch
import numpy as np
from torch.utils.data import Dataset, DataLoader
import os
import sys
sys.path.append(os.path.join(os.path.dirname(__file__), '..', '..'))
from datasets.sloper4d import SLOPER4D_Dataset
from datasets.waymo_v2 import WAYMOV2_Dataset
from datasets.humanm3 import HumanM3_Dataset
from datasets.cimi4d import CIMI4D_Dataset
from datasets.lidarh26m import LiDARH26M_Dataset
# from models.graphormer.graphormer_model import graphormer_model
# from models.unsupervised.Network import point_net_ssg, smpl_model
from models.pose_mesh_net import LiDAR_HMR
# from models.v2v_posenet import V2VPoseNet
from tqdm import tqdm
import torch.optim as optim
import logging
import torch.nn.functional as F
import argparse
from models.pmg_config import config, update_config
from scripts.eval_utils import mean_per_vertex_error, setup_seed, mean_per_edge_error, smpl_model, J_regressor, JOINTS_IDX
from models.graphormer.data.config import H36M_J17_NAME, H36M_J17_TO_J14, J24_NAME, J24_TO_J14
from fvcore.nn import FlopCountAnalysis, parameter_count_table
# from thop import profile, clever_format
from models.pct_config import pct_config, update_pct_config
import smplx

def parse_args():
    parser = argparse.ArgumentParser(description='Train keypoints network')
    parser.add_argument(
        '--dataset', default='sloper4d', required=False, type=str)
    parser.add_argument(
        '--state_dict', default='', required=False, type=str)
    parser.add_argument(
        '--cfg', default='configs/mesh/sloper4d.yaml', required=False, type=str)
    args, rest = parser.parse_known_args()
    return args

logger = logging.getLogger(__name__)

class AverageMeter(object):
    """Computes and stores the average and current value"""

    def __init__(self):
        self.reset()

    def reset(self):
        self.val = 0
        self.avg = 0
        self.sum = 0
        self.count = 0

    def update(self, val, n=1):
        self.val = val
        self.sum += val * n
        self.count += n
        self.avg = self.sum / self.count

def train(model, dataloader, optimizer, epoch):
    model.train()
    loss_all = AverageMeter()
    loss_shift = AverageMeter()
    loss_joint = AverageMeter()
    loss_vert = AverageMeter()
    PRINT_FREQ = 500
    for i, sample in enumerate(dataloader):
        for key in sample:
            if type(sample[key]) is not dict and type(sample[key]) is not list:
                sample[key] = sample[key].cuda()
        pcd = sample['human_points_local']
        torch.autograd.set_detect_anomaly(True)
        optimizer.zero_grad()

        # flops = FlopCountAnalysis(model, pcd)
        # print("FLOPs: ", flops.total() / 1e9)

        # flops, params = profile(model, inputs = (pcd,))
        # flops, params = clever_format([flops, params], "%.3f")
        # print(flops, params)
        # import pdb; pdb.set_trace()
        
        ret_dict = model(pcd)
        loss_dict = model.all_loss(ret_dict, sample)
        all_loss = loss_dict['loss']
        if epoch >= 7:
            all_loss += loss_dict['edge_loss']
            loss_dict['loss_vert'] += loss_dict['edge_loss']
            # all_loss += loss_dict['pen_loss']
            # loss_dict['loss_vert'] += loss_dict['pen_loss']
            
        all_loss.backward()
        optimizer.step()
        loss_all.update(loss_dict['loss'].item())
        loss_joint.update(loss_dict['loss_joint'].item())
        loss_shift.update(loss_dict['loss_shift'].item())
        # if 'loss_vert' in loss_dict.keys():
        # import pdb; pdb.set_trace()
        loss_vert.update(loss_dict['loss_vert'].item())
        # print(loss_dict['loss_vert'])
        if i % PRINT_FREQ == 0:
            msg = 'Epoch: [{0}][{1}/{2}]\t' \
                  'Loss_all: {loss_all.val:.3f} ({loss_all.avg:.3f})\t' \
                  'loss_shift: {loss_shift.val:.3f} ({loss_shift.avg:.3f})\t' \
                    'loss_joint: {loss_joint.val:.3f} ({loss_joint.avg:.3f})\t' \
                    'loss_vert: {loss_vert.val:.3f} ({loss_vert.avg:.3f})'.format(
                    epoch, i, len(dataloader), loss_all=loss_all, loss_shift=loss_shift, \
                        loss_joint = loss_joint, loss_vert = loss_vert)
            print(msg)
            # logger.info(msg)

def test(model, dataloader, save = False):
    model.eval()
    mpjpe = 0
    mpvpe = 0
    mpee = 0
    mpere = 0
    number = 0
    precision = 0
    print('============Testing============')
    mesh_face = model.smpl_.faces
    # save = False
    if save:
        saver_dict = {}
        saver_dict['pcd'] = []
        saver_dict['mesh_o'] = []
        saver_dict['mesh_r'] = []
        saver_dict['mesh_gt'] = []
        saver_dict['mpvpe_o'] = []
        saver_dict['mpere_o'] = []
        saver_dict['mpvpe_r'] = []
        saver_dict['mpere_r'] = []
        saver_dict['number_list'] = []
        saver_dict['pose_theta'] = []
        saver_dict['pose_beta'] = []
        saver_dict['pose_trans'] = []

    J_r = smpl_model.J_regressor.cuda()
    for sample in tqdm(dataloader):
        for key in sample:
            if type(sample[key]) is not dict and type(sample[key]) is not list:
                sample[key] = sample[key].cuda()
        pcd = sample['human_points_local']
        gt_pose = sample['smpl_joints_local']
        with torch.no_grad():
            ret_dict = model(pcd)#， sample['betas'])
        
        seg = ret_dict['seg']
        gt_seg = sample['seg_label'].to(seg.device)
        precision += (seg.argmax(dim = 1) == gt_seg).sum() / gt_seg.numel() 
        pred_vertices = ret_dict['mesh_refine']
        pose = torch.einsum('bnk,mn->bmk', [pred_vertices, J_regressor])[:,JOINTS_IDX]
        gt_vertices = sample['smpl_verts_local'].to(pred_vertices.device)
        if args.dataset == 'lidarh26m':
            pred_vertices -= pose[:,[0]]
            gt_vertices -= gt_pose[:,[0]]
            pose -= pose[:,[0]]
            gt_pose -= gt_pose[:,[0]]
        num_person = pose.shape[0]
        mpjpe += (pose - gt_pose.to(pose.device)).norm(dim = -1).mean() * num_person
        # gt_root = torch.einsum('ji,bik->bjk', [J_r, gt_vertices])[:,[0]]
        # pred_root = torch.einsum('ji,bik->bjk', [J_r, pred_vertices])[:,[0]]
        # pred_vertices -= pred_root
        # gt_vertices -= gt_root

        error_vertices = mean_per_vertex_error(pred_vertices, gt_vertices)
        error_edges, error_relative_edges = mean_per_edge_error(pred_vertices, gt_vertices, mesh_face)
        # import pdb; pdb.set_trace()
        mpvpe += error_vertices.mean() * num_person
        mpee += error_edges * num_person
        mpere += error_relative_edges.mean() * num_person
        number += num_person
        if save:
            saver_dict['pcd'].append(pcd.detach().cpu().numpy())
            saver_dict['mesh_o'].append(ret_dict['mesh_out'].detach().cpu().numpy())
            saver_dict['mesh_r'].append(ret_dict['mesh_refine'].detach().cpu().numpy())
            saver_dict['mesh_gt'].append(gt_vertices.detach().cpu().numpy())
            saver_dict['mpvpe_r'].append(error_vertices)
            saver_dict['mpere_r'].append(error_relative_edges.mean(dim = -1).numpy())

            error_vertices = mean_per_vertex_error(ret_dict['mesh_out'], gt_vertices)
            error_edges, error_relative_edges = mean_per_edge_error(ret_dict['mesh_out'], gt_vertices, mesh_face)
            saver_dict['mpvpe_o'].append(error_vertices)
            saver_dict['mpere_o'].append(error_relative_edges.mean(dim = -1).numpy())
            saver_dict['number_list'].append(sample['num_points'].cpu().numpy())
            saver_dict['pose_theta'].append(ret_dict['pose_theta'].cpu().numpy())
            saver_dict['pose_beta'].append(ret_dict['pose_beta'].cpu().numpy())
            saver_dict['pose_trans'].append(ret_dict['trans'].cpu().numpy())
        # beta_, theta_, trans_ = ret_dict['pose_beta'], ret_dict['pose_theta'], ret_dict['trans']
        # import pdb; pdb.set_trace()
        # vertices = smpl_model(transl = trans_, betas = beta_, global_orient = theta_[:,:3], body_pose = theta_[:,3:]).vertices
        # import pdb; pdb.set_trace()
    if save:
        saver_dict['mesh_o'] = np.concatenate(saver_dict['mesh_o'], axis = 0)
        saver_dict['mesh_r'] = np.concatenate(saver_dict['mesh_r'], axis = 0)
        saver_dict['mesh_gt'] = np.concatenate(saver_dict['mesh_gt'], axis = 0)
        saver_dict['mpvpe_r'] = np.concatenate(saver_dict['mpvpe_r'], axis = 0)
        saver_dict['mpere_r'] = np.concatenate(saver_dict['mpere_r'], axis = 0)
        saver_dict['mpvpe_o'] = np.concatenate(saver_dict['mpvpe_o'], axis = 0)
        saver_dict['mpere_o'] = np.concatenate(saver_dict['mpere_o'], axis = 0)
        saver_dict['pose_theta'] = np.concatenate(saver_dict['pose_theta'], axis = 0)
        saver_dict['pose_beta'] = np.concatenate(saver_dict['pose_beta'], axis = 0)
        saver_dict['pose_trans'] = np.concatenate(saver_dict['pose_trans'], axis = 0)
        saver_dict['pcd'] = np.concatenate(saver_dict['pcd'], axis = 0)
        # saver_dict['number_list'] = np.concatenate(saver_dict['number_list'], axis = 0)
        os.makedirs('save_meshik/', exist_ok=True)
        np.save('save_meshik/'+dataset_task+'.npy', np.array(saver_dict))
    mpjpe = mpjpe.item() / number    
    precision = precision.item() / number
    mpvpe = mpvpe.item() / number
    mpee = mpee.item() / number
    mpere = mpere.item() / number
    return mpjpe, precision, mpvpe, mpee, mpere

args = parse_args()
setup_seed(10)
dataset_task = args.dataset #'sloper4d', 'waymov2', 'collect'
if dataset_task == 'sloper4d':
    scene_train = [
            'seq002_football_001',
            'seq003_street_002',
            'seq005_library_002',
            'seq007_garden_001',
            'seq008_running_001'
        ]
    scene_test = ['seq009_running_002']
    dataset_root = "/app/data/sloper4d/"
    train_dataset = SLOPER4D_Dataset(dataset_root, scene_train, is_train = True, dataset_path = './save_data/sloper4d/',
                                return_torch=False, device = 'cuda',
                                fix_pts_num=True, return_smpl = True, augmentation = True, interval = 5)
    test_dataset = SLOPER4D_Dataset(dataset_root, scene_test, is_train = False, dataset_path = './save_data/sloper4d/',
                                return_torch=False, device = 'cuda',
                                fix_pts_num=True, return_smpl = True, interval = 5)
    num_keypoints = 15

elif dataset_task == 'waymov2':
    dataset_root = '/Extra/fanbohao/posedataset/PointC/Waymo/resave_files/'
    train_dataset = WAYMOV2_Dataset(dataset_root, is_train = True, dataset_path = './save_data/waymov2/',
                                return_torch=True, device = 'cuda',
                                fix_pts_num=True, augmentation = True)
    test_dataset = WAYMOV2_Dataset(dataset_root, is_train = False, dataset_path = './save_data/waymov2/',
                                return_torch=True, device = 'cuda',
                                fix_pts_num=True)
    num_keypoints = 15

elif dataset_task == 'humanm3':
    train_dataset = HumanM3_Dataset(is_train = True,
                                return_torch=True, device = 'cuda',
                                fix_pts_num=True, augmentation = True, interval = 5)
    test_dataset = HumanM3_Dataset(is_train = False,
                                return_torch=True, device = 'cuda',
                                fix_pts_num=True, interval = 5)
    num_keypoints = 15

elif dataset_task == 'cimi4d':
    train_dataset = CIMI4D_Dataset(is_train = True,
                                return_torch=True, device = 'cuda',
                                fix_pts_num=True, augmentation = True, interval = 5)
    test_dataset = CIMI4D_Dataset(is_train = False,
                                return_torch=True, device = 'cuda',
                                fix_pts_num=True, interval = 5)
    num_keypoints = 15

elif dataset_task == 'lidarh26m':
    train_dataset = LiDARH26M_Dataset(is_train = True,
                                return_torch=True, device = 'cuda',
                                fix_pts_num=True, augmentation = True, interval = 5)
    test_dataset = LiDARH26M_Dataset(is_train = False,
                                return_torch=True, device = 'cuda',
                                fix_pts_num=True, interval = 5)
    num_keypoints = 15

# model = pose_meshformer().cuda()
config_name = args.cfg.split('/')[-1].split('.')[0]
update_config(args.cfg)
model = LiDAR_HMR(pmg_cfg = config, train_pmg = True).cuda()
# model = LiDAR_HMR(pct_config).cuda()

total = sum([param.nelement() for param in model.parameters()])
bs = 8
# train_loader = DataLoader(train_dataset, batch_size=bs, shuffle=True, num_workers = 8)
test_loader = DataLoader(test_dataset, batch_size=bs, shuffle=False, num_workers = 0)
optimizer = torch.optim.Adam(params=list(model.parameters()),
                                           lr=5e-4,
                                           betas=(0.9, 0.999),
                                           weight_decay=0)
epoch_now = -1

if args.state_dict != '':
    state_dict = torch.load(args.state_dict)
    model.load_state_dict(state_dict['net'])
    
save = True

mpjpe, precision, mpvpe, mpee, mpere = test(model, test_loader, save)

print('MPJPE: '+str(mpjpe) + '; Precision:' + str(precision) + '; MPVPE:'+str(mpvpe) + '; MPERE:'+str(mpere))
# save = False
# if save:
#     np.save('statistics/'+str(args.dataset)+'.npy', np.array(sta_dict))