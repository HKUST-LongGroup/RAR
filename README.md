<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="static/readme/title_dark.svg">
  <img src="static/readme/title_light.svg" width="680" alt="RAR: Rate-Adaptive Rollout for Time-Consistent Interactive World Models">
</picture>

<p>
Yaoyang Liu<sup>1*</sup> &nbsp;·&nbsp; Dongyu Yan<sup>2*</sup> &nbsp;·&nbsp; Yihua Du<sup>2</sup> &nbsp;·&nbsp; Shengju Qian<sup>3</sup><br>
Zeke Xie<sup>2</sup> &nbsp;·&nbsp; Xin Wang<sup>3</sup> &nbsp;·&nbsp; Ying-Cong Chen<sup>2</sup> &nbsp;·&nbsp; Long Chen<sup>1&dagger;</sup>
</p>

<p>
<sup>1</sup>HKUST &nbsp;&nbsp; <sup>2</sup>HKUST (GZ) &nbsp;&nbsp; <sup>3</sup>Tencent LightSpeed<br>
<sub><sup>*</sup>Equal contribution &nbsp;&nbsp; <sup>&dagger;</sup>Corresponding author</sub>
</p>

<!-- TODO before going public: fill in the arXiv ID (button + BibTeX) and link the code -->
<a href="https://lazysheeeeeep.github.io/RAR/"><picture><source media="(prefers-color-scheme: dark)" srcset="static/readme/btn_page_dark.svg"><img src="static/readme/btn_page_light.svg" height="38" alt="Project Page"></picture></a>&nbsp;
<a href="https://arxiv.org/abs/XXXX.XXXXX"><picture><source media="(prefers-color-scheme: dark)" srcset="static/readme/btn_arxiv_dark.svg"><img src="static/readme/btn_arxiv_light.svg" height="38" alt="arXiv"></picture></a>&nbsp;
<picture><source media="(prefers-color-scheme: dark)" srcset="static/readme/btn_code_dark.svg"><img src="static/readme/btn_code_light.svg" height="38" alt="Code (coming soon)"></picture>

</div>

<br>

<p align="center">
  <img src="static/readme/teaser.webp" width="100%" alt="One RAR model following a changing target generation rate on Doom, CS2 and FPV">
</p>
<p align="center"><sub>
One RAR model steers its generation rate <b>while it generates</b>, following the target-FPS curve under each clip.
The clips play at a fixed 30 FPS, so a high target rate makes the world look slower and a low one makes it look faster.
</sub></p>

> **TL;DR** &nbsp; Interactive world models are usually locked to one temporal rate, so the pace of the generated world
> depends on how fast the hardware runs, and fine motion competes with long horizons. **RAR** puts frames from every rate
> on a shared physical-time axis (**Stride-RoPE**) and trains on several strides at once. One model can then generate at
> any rate in its range, including unseen ones, and change the rate on the fly.

## News

<!-- TODO: adjust the dates when the repository goes public -->
- **2026.10** &nbsp; The [project page](https://lazysheeeeeep.github.io/RAR/) is online, with interactive demos for every experiment.
- **Coming soon** &nbsp; The arXiv preprint and the code.

## Highlights

### One model, any rollout rate

The same RAR model rolls out at its training rates and at intermediate rates it never saw in training. Starting from the
same frame and following the same controls, every rate shows the same scene at the same physical time. A higher rate
just produces more frames along the way.

<p align="center"><img src="static/readme/multirate.webp" width="100%" alt="Three rollout rates per environment on one physical clock"></p>

<details>
<summary>Quantitative results on Doom, CS2 and FPV</summary>
<br>

The number of generated frames is fixed within each environment. Drift is the ratio of last-quarter to first-quarter
LPIPS. SR measures rate fidelity, with an ideal value of 1.

| Environment | FPS | Type | Horizon (s) | LPIPS ↓ | Drift | DOVER ↑ | SR → 1 |
|:--|--:|:--|--:|--:|--:|--:|--:|
| Doom | 14 | Train | 15.1 | 0.4279 | 1.17 | 0.3205 | 0.923 |
| | 28 | Interp. | 7.6 | 0.4179 | 1.22 | 0.3269 | 1.003 |
| | 35 | Train | 6.1 | 0.3991 | 1.27 | 0.3153 | 0.999 |
| | 49 | Interp. | 4.3 | 0.4003 | 1.26 | 0.3156 | 0.986 |
| | 70 | Train | 3.0 | 0.3852 | 1.34 | 0.3049 | 1.082 |
| CS2 | 16 | Train | 15.0 | 0.6489 | 1.52 | 0.3928 | 0.983 |
| | 24 | Interp. | 10.0 | 0.6200 | 1.60 | 0.4187 | 1.009 |
| | 32 | Train | 7.5 | 0.5980 | 1.61 | 0.4402 | 0.970 |
| | 48 | Interp. | 5.0 | 0.5944 | 1.67 | 0.4369 | 1.024 |
| | 64 | Train | 3.8 | 0.5823 | 1.69 | 0.4323 | 1.097 |
| FPV | 20 | Train | 12.0 | 0.5247 | 1.35 | 0.2827 | 1.031 |
| | 30 | Train | 8.0 | 0.5161 | 1.41 | 0.2766 | 1.040 |
| | 40 | Interp. | 6.0 | 0.5011 | 1.42 | 0.2733 | 0.960 |
| | 50 | Interp. | 4.8 | 0.5035 | 1.45 | 0.2843 | 1.007 |
| | 60 | Train | 4.0 | 0.4944 | 1.49 | 0.2956 | 0.917 |

</details>

### Change the rate mid-rollout

The target rate can change inside one continuous rollout, without clearing the KV cache or restarting generation. The
stride measured from optical flow (solid) follows the requested schedule (dashed), whether it changes smoothly or jumps,
with a Pearson correlation of up to 0.998.

<p align="center">
  <img src="static/images/switch/fpv_smooth.png" width="40%" alt="FPV, smooth schedule">&nbsp;
  <img src="static/images/switch/fpv_abrupt.png" width="40%" alt="FPV, abrupt schedule">
</p>

### Longer horizons for the same budget

Coarse strides cover more physical time with the same number of frames. Under matched wall-clock time on Doom, a
213-frame RAR model beats 70 FPS baselines trained on 425- and 849-frame windows, which cost 1.56× and 5.25× more time
per update.

<p align="center"><img src="static/images/eff_fixed_time.png" width="80%" alt="LPIPS under matched wall-clock time"></p>

### Plug into pretrained world models

Two short fine-tuning stages (3k steps each) turn the pretrained SANA-WM into a multi-rate streaming model, and LPIPS
improves at every rate. The videos are on the [project page](https://lazysheeeeeep.github.io/RAR/#sana).

## How it works

A clip sampled at rate $f$ has temporal stride $s = f_{\mathrm{base}} / f$. **Stride-RoPE** places latent frame $n$ at
temporal position $p_n = n\,s$, so equal gaps in physical time give equal rotary phases at every rate. It adds no
parameters and reduces to standard RoPE at $f = f_{\mathrm{base}}$.

<p align="center"><img src="static/images/stride_rope.png" width="88%" alt="Stride-RoPE"></p>

During training, videos and their controls are sampled together at several strides, always with the same number of
frames: fine strides learn fast dynamics, and coarse strides reach longer horizons at no extra cost. At rollout time the
stride sets the rate, and since positions simply accumulate the strides ($p_{n+1} = p_n + s_n$), the rate can change at
any step.

<details>
<summary>Framework overview</summary>
<br>
<p align="center"><img src="static/images/pipeline.png" width="70%" alt="RAR framework"></p>
</details>

<details>
<summary>Abstract</summary>
<br>

Video-based interactive world models aim to enable real-time, user-controllable environments. Yet most existing systems
are trained and rolled out at a fixed temporal rate, limiting both runtime-rate adaptation and physical-horizon
coverage, a limitation we term **temporal-rate coupling**. Specifically, when runtime generation throughput differs
from the learned temporal rate, the generated world evolves unintentionally more slowly or quickly. Moreover, using a
single temporal rate imposes an inherent trade-off between temporal granularity and physical horizon: higher rates
capture finer motion but cover a shorter duration under a fixed context window. To address both limitations, we
introduce **Rate-Adaptive Rollout (RAR)**, a framework that enables interactive world models to roll out at
controllable temporal rates. At its core, *Stride-RoPE* aligns latent frames sampled at different rates on a shared
physical-time coordinate, enabling consistent multi-rate rollout, unseen-rate generalization, and online rate switching
without discarding history. Meanwhile, RAR uses multi-stride video sampling to enable joint learning of fine-grained
dynamics and long-horizon evolution. Across action- and camera-controlled environments, RAR achieves temporally
consistent multi-rate rollout and online rate switching while preserving high-rate generation quality and extending
physical horizons under matched training budgets. RAR also transfers to pretrained world models while preserving
perceptual quality.

</details>

## Citation

If you find RAR useful, please consider citing:

```bibtex
@article{liu2026rar,
  title   = {RAR: Rate-Adaptive Rollout for Time-Consistent Interactive World Models},
  author  = {Liu, Yaoyang and Yan, Dongyu and Du, Yihua and Qian, Shengju and
             Xie, Zeke and Wang, Xin and Chen, Ying-Cong and Chen, Long},
  journal = {arXiv preprint arXiv:XXXX.XXXXX},
  year    = {2026}
}
```

<sub>The project page and its content are licensed under [CC BY-SA 4.0](https://creativecommons.org/licenses/by-sa/4.0/).</sub>
