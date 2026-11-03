"""Mask-aware disease and independently supervised event-risk heads."""
import torch
from torch import nn


class ResidualBlock(nn.Module):
    def __init__(self, size):
        super().__init__()
        self.net = nn.Sequential(nn.Linear(size, size), nn.BatchNorm1d(size), nn.SiLU(), nn.Dropout(0.2))

    def forward(self, x):
        return x + self.net(x)


class FusionModel(nn.Module):
    def __init__(self, ecg_dim: int, tab_dim: int, disease_count: int, risk_head: bool = False):
        super().__init__()
        self.ecg = nn.Linear(ecg_dim, 128)
        self.tab = nn.Sequential(nn.Linear(tab_dim, 128), nn.SiLU(), ResidualBlock(128))
        self.gate = nn.Sequential(nn.Linear(258, 128), nn.SiLU(), nn.Linear(128, 2))
        self.disease = nn.Linear(128, disease_count)
        self.risk = nn.Linear(128, 1) if risk_head else None

    def forward(self, ecg, tab, mask_ecg, mask_tab, modality_dropout=False):
        if modality_dropout and self.training:
            mask_ecg = mask_ecg * (torch.rand_like(mask_ecg) >= 0.3)
            tab = tab * (torch.rand_like(tab) >= 0.3)
        a = self.ecg(ecg) * mask_ecg
        b = self.tab(tab) * mask_tab
        masks = torch.cat([mask_ecg, mask_tab], dim=1)
        gate = self.gate(torch.cat([a, b, masks], dim=1))
        gate = gate.masked_fill(masks == 0, -1e4).softmax(dim=1)
        fused = gate[:, :1] * a + gate[:, 1:] * b
        disease = self.disease(fused)
        risk = self.risk(fused) if self.risk is not None else None
        return disease, risk
