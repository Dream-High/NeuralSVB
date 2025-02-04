from utils.indexed_datasets import IndexedDataset
from tqdm import tqdm
from modules.voice_conversion.dtw.align import align_from_distances
import torch
import matplotlib.pyplot as plt
import torch.nn.functional as F
import math
import time
import os
from multiprocessing import Pool
from utils.pitch_utils import f0_to_coarse, denorm_f0
import numpy as np

from tasks.singing.neural_svb_task import FastSingingDataset
from utils.hparams import hparams, set_hparams



## here is API for one sample
def NaiveDTW(src, tgt, input):
    # src: [S, H]
    # tgt: [T, H]
    dists = torch.cdist(src.unsqueeze(0), tgt.unsqueeze(0))  # [1, S, T]
    costs = dists.squeeze(0)  # [S, T]
    alignment = align_from_distances(costs.T.cpu().detach().numpy())
    output = input[alignment]
    return output, alignment

## here is API for one sample  (Zero meaned )
def ZMNaiveDTW(src, tgt, input):
    # src: [S, H]
    # tgt: [T, H]
    src = (src - src.mean())#/src.std()
    tgt = (tgt - tgt.mean())#/tgt.std()
    dists = torch.cdist(src.unsqueeze(0)[:, :, None], tgt.unsqueeze(0)[:, :, None])  # [1, S, T]
    costs = dists.squeeze(0)  # [S, T]
    alignment = align_from_distances(costs.T.cpu().detach().numpy())
    output = input[alignment]
    return output, alignment

## here is API for one sample  (Normalized )
def NNaiveDTW(src, tgt, input):
    # src: [S, H]
    # tgt: [T, H]
    src = (src - src.mean()) / (src.std() + 0.00000001)
    tgt = (tgt - tgt.mean()) / (tgt.std() + 0.00000001)
    dists = torch.cdist(src.unsqueeze(0)[:, :, None], tgt.unsqueeze(0)[:, :, None])  # [1, S, T]
    costs = dists.squeeze(0)  # [S, T]
    alignment = align_from_distances(costs.T.cpu().detach().numpy())
    output = input[alignment]
    return output, alignment

if __name__ == '__main__':
    # code for visualization
    def spec_to_figure(spec, vmin=None, vmax=None, name=''):
        if isinstance(spec, torch.Tensor):
            spec = spec.cpu().numpy()
        fig = plt.figure(figsize=(12, 6))
        plt.pcolor(spec.T, vmin=vmin, vmax=vmax)
        plt.savefig(os.path.join('tmp', name))
        return fig

    def f0_to_figure(f0_src, f0_aligned=None, f0_prof=None, name='f0.png'):
        fig = plt.figure(figsize=(12, 8))
        f0_src = f0_src.cpu().numpy()
        f0_src[f0_src == 0] = np.nan
        plt.plot(f0_src, color='r', label='src')
        if f0_aligned is not None:
            f0_aligned = f0_aligned.cpu().numpy()
            f0_aligned[f0_aligned == 0] = np.nan
            plt.plot(f0_aligned, color='b', label='f0_aligned')
        if f0_prof is not None:
            f0_pred = f0_prof.cpu().numpy()
            f0_prof[f0_prof == 0] = np.nan
            plt.plot(f0_pred, color='green', label='profession')
        plt.legend()
        plt.savefig(os.path.join('tmp', name))
        return fig

    set_hparams()

    train_ds = FastSingingDataset('test')

    # Test One sample case
    sample = train_ds[0]
    amateur_f0 = sample['f0']
    prof_f0 = sample['prof_f0']

    amateur_uv = sample['uv']
    amateur_padding = sample['mel2ph'] == 0
    prof_uv = sample['prof_uv']
    prof_padding = sample['prof_mel2ph'] == 0
    amateur_f0_denorm = denorm_f0(amateur_f0, amateur_uv, hparams, pitch_padding=amateur_padding)
    prof_f0_denorm = denorm_f0(prof_f0, prof_uv, hparams, pitch_padding=prof_padding)

    # 用normed_interpolated_f0 如下, 效果更差，下降20个acc..
    # amateur_f0_denorm = amateur_f0 #denorm_f0(amateur_f0, amateur_uv, hparams, pitch_padding=amateur_padding)
    # prof_f0_denorm = prof_f0 #denorm_f0(prof_f0, prof_uv, hparams, pitch_padding=prof_padding)

    amateur_mel = sample['mel']
    prof_mel = sample['prof_mel']
    pad_num = max(prof_mel.shape[0] - amateur_mel.shape[0], 0)
    amateur_mel_padded = F.pad(amateur_mel, [0, 0, 0, pad_num])[:prof_mel.shape[0], :]
    # aligned_mel, alignment = NaiveDTW(amateur_f0_denorm, prof_f0_denorm, amateur_mel)
    # aligned_f0_denorm, alignment = NaiveDTW(amateur_f0_denorm, prof_f0_denorm, amateur_f0_denorm)
    aligned_mel, alignment = ZMNaiveDTW(amateur_f0_denorm, prof_f0_denorm, amateur_mel)
    aligned_f0_denorm, alignment = ZMNaiveDTW(amateur_f0_denorm, prof_f0_denorm, amateur_f0_denorm)
    cat_spec = torch.cat([amateur_mel_padded, aligned_mel, prof_mel], dim=-1)
    spec_to_figure(cat_spec, name=f'f0_denorm_mel_Cn.png')
    # f0 align f0
    f0_to_figure(f0_src=amateur_f0_denorm, f0_aligned=aligned_f0_denorm, f0_prof=prof_f0_denorm,
                 name=f'f0_denorm_f0_Cn.png')
    amateur_mel2ph = sample['mel2ph']
    prof_mel2ph = sample['prof_mel2ph']
    aligned_mel2ph = amateur_mel2ph[alignment]
    acc = (prof_mel2ph == aligned_mel2ph).sum().cpu().numpy() / (
            prof_mel2ph != 0).sum().cpu().numpy()
    print(acc)
    exit()

# python modules/voice_conversion/dtw/naive_dtw.py --config egs/datasets/audio/PopBuTFy/svc_ppg.yaml