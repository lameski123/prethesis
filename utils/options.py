import argparse


def create_parser():
    parser = argparse.ArgumentParser(description='Spine Registration')
    parser.add_argument('--exp_name', type=str, default='flownet3d', metavar='N', help='Name of the experiment')
    parser.add_argument('--model', type=str, default='flownet', metavar='N', choices=['flownet'], help='Model to use, [flownet]')
    parser.add_argument('--emb_dims', type=int, default=512, metavar='N', help='Dimension of embeddings')
    parser.add_argument('--num_points', type=int, default=4096, help='Point Number [default: 4096]')
    parser.add_argument('--dropout', type=float, default=0.5, metavar='N', help='Dropout ratio in transformer')
    parser.add_argument('--batch_size', type=int, default=4, metavar='batch_size', help='Size of batch)')
    parser.add_argument('--test_batch_size', type=int, default=4, metavar='batch_size', help='Size of batch)')
    parser.add_argument('--epochs', type=int, default=100, metavar='N', help='number of episode to train')
    parser.add_argument('--use_sgd', action='store_true', default=False, help='Use SGD')
    parser.add_argument('--lr', type=float, default=0.001, metavar='LR', help='learning rate (default: 0.001, 0.1 if using sgd)')
    parser.add_argument('--momentum', type=float, default=0.9, metavar='M', help='SGD momentum (default: 0.9)')
    parser.add_argument('--no_cuda', action='store_true', default=False, help='enables CUDA training')
    parser.add_argument('--seed', type=int, default=100, metavar='S', help='random seed (default: 100)')
    parser.add_argument('--num_workers', type=int, default=4, metavar='S', help='num of workers for dataloader (default: 4)')
    parser.add_argument('--eval', action='store_true', default=False, help='evaluate the model')
    parser.add_argument('--cycle', type=bool, default=False, metavar='N', help='Whether to use cycle consistency')
    parser.add_argument('--gaussian_noise', type=bool, default=False, metavar='N', help='Wheter to add gaussian noise')
    parser.add_argument('--dataset', type=str, default='SceneflowDataset', choices=['SceneflowDataset'], metavar='N', help='dataset to use')
    parser.add_argument('--dataset_path', type=str, default='./spine_clouds', metavar='N', help='dataset to use')
    parser.add_argument('--augment_test', action='store_true', help='augment test data with rotation')
    parser.add_argument('--max_rotation', type=float, default=20, metavar='M', help='maximum rotation degree (default: 20)')
    parser.add_argument('--test_rotation_axis', type=str, choices=['x', 'y', 'z'], default=None, help='around which axis to rotate the data [default: None]')
    parser.add_argument('--use_raycasted_data', action='store_true', help='train on raycasted')
    parser.add_argument('--no_augmentation', action='store_true', help='augment training data')
    parser.add_argument('--data_seed', type=int, choices=[0, 1, 2, 3, 4], default=0, help='determines dataset slicing indices [default: 0]')
    parser.add_argument('--test_id', type=int, default=None, help='spine id to choose for one leave out testing [default: None]')
    parser.add_argument('--model_path', type=str, default='', metavar='N', help='Pretrained model path')
    parser.add_argument('--test_output_path', type=str, required=False, metavar='N', help='Path to save the test results')
    parser.add_argument('--no_legacy_model', action='store_true', help='use legacy model in test mode')
    parser.add_argument('--loss', nargs='+', default=[], help='list of possible losses, currently [biomechanical, rigidity, chamfer] or leave it empty only for flow loss')
    parser.add_argument('--loss_coeff', nargs='+', default=[], help='list of coefficients for each loss, in the same order as the loss')
    parser.add_argument('--gpu_id', type=int, default=-1, metavar='S', help='GPU id (default: -1)')
    parser.add_argument('--wandb_key', type=str, required=True, help='key to login to your wandb account')
    parser.add_argument('--wandb_sweep_id', type=str, default=None, help='sweep id for wandb')
    parser.add_argument('--wandb_sweep_count', type=int, default=10, help='number of times sweeping the HP range')
    parser.add_argument('--sweep_target_loss', type=str, default='total_loss', choices=['total_loss', 'mse_loss', 'biomechanical_loss', 'rigid_loss', 'chamfer_loss', 'quaternion_distance', 'translation_distance'], help='which loss to use as target for sweep')
    return parser
