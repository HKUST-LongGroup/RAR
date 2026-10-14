<div align="center">

<picture>
  <source media="(prefers-color-scheme: dark)" srcset="static/readme/title_dark.svg">
  <img src="static/readme/title_light.svg" width="680" alt="RAR: Rate-Adaptive Rollout for Time-Consistent Interactive World Models">
</picture>

<p>
Yaoyang Liu<sup>1*</sup>, Dongyu Yan<sup>2*</sup>, Yihua Du<sup>2</sup>, Shengju Qian<sup>3</sup>, Zeke Xie<sup>2</sup>, Xin Wang<sup>3</sup>, Ying-Cong Chen<sup>2</sup>, Long Chen<sup>1&dagger;</sup>
</p>

<p>
<sup>1</sup>HKUST &nbsp;&nbsp; <sup>2</sup>HKUST (GZ) &nbsp;&nbsp; <sup>3</sup>LIGHTSPEED<br>
<sub><sup>*</sup>Equal contribution &nbsp;&nbsp; <sup>&dagger;</sup>Corresponding author</sub>
</p>

<a href="https://hkust-longgroup.github.io/RAR/"><picture><source media="(prefers-color-scheme: dark)" srcset="static/readme/btn_page_dark.svg"><img src="static/readme/btn_page_light.svg" height="38" alt="Project Page"></picture></a>&nbsp;
<a href="https://arxiv.org/abs/2610.16302"><picture><source media="(prefers-color-scheme: dark)" srcset="static/readme/btn_arxiv_dark.svg"><img src="static/readme/btn_arxiv_light.svg" height="38" alt="arXiv"></picture></a>

</div>

<br>

<p align="center">
  <img src="static/readme/teaser.webp" width="100%" alt="One RAR model following a changing target generation rate on Doom, CS2 and FPV">
</p>
<p align="center"><sub>
One model steers its generation rate <b>while it generates</b>. Clips play at a fixed frame rate, so the world slows down
when the target rate is high and speeds up when it is low.
</sub></p>

## 💡 TL;DR

Interactive world models are usually locked to one temporal rate. **RAR** puts frames from every rate on a shared
physical-time axis (**Stride-RoPE**) and trains on several strides at once, so **one model can roll out at any rate and
change it on the fly**.

## 📣 News

- **2026.10** &nbsp; The paper is on [arXiv](https://arxiv.org/abs/2610.16302), and the [project page](https://hkust-longgroup.github.io/RAR/) is online.
- **Coming soon** &nbsp; The inference code.

## ✨ Highlights

- 🎚️ **One model, any rollout rate**, including rates never seen in training.
- 🔀 **Switch rates mid-rollout**, without resetting the KV cache.
- 🔭 **Longer physical horizons** for the same training budget.
- 🧩 **Plugs into pretrained world models** with a short fine-tune.

<p align="center"><img src="static/readme/multirate.webp" width="100%" alt="Three rollout rates per environment on one physical clock"></p>
<p align="center"><sub>Three rollout rates, one physical clock: every rate shows the same scene at the same moment.</sub></p>

## 🛠️ Method

**Stride-RoPE** places each frame at its physical time instead of its index, so frames sampled at different rates share
one temporal axis. Training mixes several strides, and at rollout time the stride sets the rate.

<p align="center"><img src="static/images/stride_rope.png" width="88%" alt="Stride-RoPE"></p>

## 📝 TODO

- [x] Release project page
- [x] Release arXiv paper
- [ ] Release inference code

## 📖 Citation

```bibtex
@article{liu2026rar,
  title   = {RAR: Rate-Adaptive Rollout for Time-Consistent Interactive World Models},
  author  = {Liu, Yaoyang and Yan, Dongyu and Du, Yihua and Qian, Shengju and
             Xie, Zeke and Wang, Xin and Chen, Ying-Cong and Chen, Long},
  journal = {arXiv preprint arXiv:2610.16302},
  year    = {2026}
}
```
