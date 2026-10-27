"""Real-ESRGAN (realesr-general-x4v3, SRVGGNetCompact) 4x upscaler for raw RGB frames."""
import numpy as np, torch, torch.nn as nn, torch.nn.functional as F


class SRVGGNetCompact(nn.Module):
    def __init__(self, num_feat=64, num_conv=32, upscale=4):
        super().__init__()
        self.upscale = upscale
        body = [nn.Conv2d(3, num_feat, 3, 1, 1), nn.PReLU(num_feat)]
        for _ in range(num_conv):
            body += [nn.Conv2d(num_feat, num_feat, 3, 1, 1), nn.PReLU(num_feat)]
        body.append(nn.Conv2d(num_feat, 3 * upscale * upscale, 3, 1, 1))
        self.body = nn.ModuleList(body)
        self.upsampler = nn.PixelShuffle(upscale)

    def forward(self, x):
        out = x
        for layer in self.body:
            out = layer(out)
        return self.upsampler(out) + F.interpolate(x, scale_factor=self.upscale, mode="nearest")


class Upscaler:
    def __init__(self, weights, threads=4):
        torch.set_num_threads(threads)
        self.net = SRVGGNetCompact()
        state = torch.load(weights, map_location="cpu", weights_only=True)
        self.net.load_state_dict(state.get("params", state))
        self.net.eval().to(memory_format=torch.channels_last)  # ~1.6x faster on CPU

    @torch.inference_mode()
    def __call__(self, frame):
        """HxWx3 RGB (uint8, or uint16 for 10-bit HDR) -> same dtype at (4H)x(4W)x3"""
        peak = 65535 if frame.dtype == np.uint16 else 255
        x = torch.from_numpy(frame.astype(np.float32)).permute(2, 0, 1).div_(peak).unsqueeze(0)
        y = self.net(x.contiguous(memory_format=torch.channels_last)).clamp_(0, 1).mul_(peak).round_()
        return y[0].permute(1, 2, 0).contiguous().numpy().astype(frame.dtype)
