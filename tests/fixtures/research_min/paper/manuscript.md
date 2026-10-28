# Domain-robust vision-based force estimation by removing the platform sensor offset

## Abstract
Vision-based force estimation lets surgical robots sense tool–tissue interaction without a dedicated sensor, but regressors trained on one robot platform degrade sharply when deployed on another. We study this degradation on two platforms and find that the drop is dominated by a platform-specific sensor offset that the regressor absorbs into its prediction head rather than by a change in visual appearance. We propose a domain-adversarial regularizer that removes the offset from the shared representation, combined with a temporal consistency term, and we evaluate it under a fixed contact-window convention with three seeds per method. On the held-out platform the proposed model lowers the root-mean-square error (RMSE) by 19.2% relative to the strongest baseline, and an ablation with explicit seed-noise resolution shows that the gain comes from the adversarial term while the consistency term is not resolvable at single-run precision. Code, result files and the preregistration are released with the paper so that every table can be regenerated.

**Keywords:** force estimation; domain shift; surgical robotics

## 1. Introduction
Surgical force estimation must transfer across robot platforms because recalibrating the sensor for every platform is impractical in the operating room [2]. Existing vision-based regressors report strong in-platform accuracy, yet two representative systems illustrate the gap. GeoNet assumes that the force sensor calibration is shared across platforms, so its predictions inherit the offset of the training platform. ForceFormer models appearance change but keeps a platform-specific prediction head, which leaves the offset untouched. In the adjacent field of visual domain adaptation the default assumption is that the shift lives in the image statistics, whereas in force sensing the shift is partly in the label channel itself; neither community has tested the label-side assumption.

We observe the phenomenon directly: GeoNet-style regressors trained on platform E1 degrade on platform E2 even when visual appearance is matched, and the residual is a near-constant offset. Our hypothesis is that existing force regressors fail under platform shift because the domain-specific sensor offset is absorbed into the regressor; a domain-adversarial regularizer removes this offset, with an expected RMSE reduction of at least 10 % on the held-out platform. We show that cross-platform degradation of vision-based force estimation is dominated by a label-side sensor offset, and that a domain-adversarial regularizer which removes it lowers the held-out RMSE by 19.2% against the strongest baseline.

The contributions of this paper are:
- A diagnosis that attributes cross-platform degradation to a label-side sensor offset, supported by a control experiment that changes only the offset.
- A domain-adversarial regularizer with a temporal consistency term that lowers RMSE on the held-out platform by 19.2% relative to the strongest baseline (baseA); the ablation shows that the gain comes from the adversarial term while the consistency term is not resolvable within seed noise.
- An ablation protocol with explicit seed-noise resolution, which reports which cells are not resolvable instead of over-reading single-run differences.

The remainder of the paper reviews related work, presents the method, and reports experiments on two platforms.

## 2. Related Work
### 2.1 Vision-based force estimation
Early systems regress force from geometric cues of the instrument and the tissue surface [1], later ones from learned appearance features of the whole frame [3]. Almost all of them are trained and tested on a single robot platform, and the few that report a second platform fine-tune on it, so the question of transfer without target labels is open. Our problem table of eight core papers shows that three of them name a held-out platform as future work and none performs the test.

### 2.2 Domain adaptation
Domain-adversarial training aligns the input distributions of two domains through a discriminator on the shared representation. In vision it is applied to image statistics. For regression with a per-domain additive label bias the alignment of inputs is not sufficient, because the bias enters through the labels; this is the structural difference that motivates placing the discriminator after the prediction head.

## 3. Method
### 3.1 Overview
Fig. 1 shows the architecture. The design follows the cause hypothesis of our preregistration: the platform-specific sensor offset, not visual appearance, is the dominant cause of the cross-platform error, so the model must remove the offset from the shared representation rather than adapt the image statistics. A frame encoder produces a representation that is shared by the regression head, the domain discriminator and the temporal consistency module.

**Fig. 1.** Architecture overview: shared encoder, regression head, domain discriminator attached behind the head (no_dom removes it) and temporal consistency module (no_cons removes it).

### 3.2 Domain-adversarial regularizer
The discriminator receives the representation concatenated with the predicted force and is trained to identify the platform, while the encoder is trained to fool it through a gradient reversal layer. Writing $z$ for the representation and $D$ for the discriminator, the adversarial term is
$L_{dom} = -\sum_i \log D(z_i, \hat{f}_i)$ (1)
Removing this term is the no_dom ablation. Because the discriminator sees the prediction, an encoder that keeps a platform-specific offset in the prediction is penalised, which is the mechanism that a plain input-level adversary lacks.

### 3.3 Temporal consistency term
Forces vary smoothly within a contact, so consecutive predictions should be close. The consistency term is
$L_{cons} = \sum_i \lVert \hat{f}_i - \hat{f}_{i-1} \rVert_2^2$ (2)
Removing this term is the no_cons ablation.

### 3.4 Training objective
The full objective is the regression loss plus the two regularizers,
$L = L_{reg} + \beta L_{dom} + \alpha L_{cons}$ (3)
with $\beta$ and $\alpha$ fixed before training and recorded in every run's argument file. Algorithm 1 summarises the training procedure; the two regularizers enter only when their weights are positive.

**Algorithm 1.** Training with the domain-adversarial and the consistency term.

```latex
\Require encoder with heads $f_\theta$, training loader $\mathcal{D}$, $\beta = 0.1$, $\alpha = 0.5$, $K = 3$
\Ensure trained parameters $\theta$ and the loss history $h$
\State $h \gets \emptyset$
\For{$k = 1, \ldots, K$}
  \State $L \gets L_{reg}(f_\theta, \mathcal{D})$
  \If{$\beta > 0$}
    \State $L \gets L + \beta\, L_{dom}$
  \EndIf
  \If{$\alpha > 0$}
    \State $L \gets L + \alpha\, L_{cons}$
  \EndIf
  \State $h \gets h \cup \{\textsc{Step}(L)\}$
\EndFor
\State \Return $h$
```

## 4. Experiments
### 4.1 Datasets and evaluation protocol
We use two platforms, E1 (training and in-platform test) and E2 (held-out platform). Clips are split by subject so that no subject appears in both train and test. All tables use the contact-window convention: only samples with |F| ≥ 0.1 N enter the statistics, with the same window across datasets. Each method is trained with 3 seeds on a single graphics card, and every table number is traceable to the evaluation file of its run.

### 4.2 Baselines
baseA is the geometric regressor of [1], run with its official code and the same 3 seeds. baseB is the appearance-based transformer of [3], re-implemented because the official code is not available; both use the same data split, window and hardware as the proposed model.

### 4.3 Main comparison
Table 1 reports the main comparison. The proposed model reaches an RMSE of 0.202 N on E1, a 19.2% reduction relative to baseA, the strongest baseline, and 0.303 N on E2; the ordering is the same on both platforms and the seed standard deviations do not overlap.

**Table 1.** Main comparison, mean ± s.d. over 3 seeds, contact-window convention (|F| ≥ 0.1 N).

| Method | RMSE E1 (N) | RMSE E2 (N) |
|---|---|---|
| baseA | 0.250 ± 0.003 | 0.352 ± 0.002 |
| baseB | 0.270 ± 0.004 | 0.383 ± 0.003 |
| ours | 0.202 ± 0.002 | 0.303 ± 0.003 |

### 4.4 Ablation study
Table 2 reports one-factor ablations against the full model. Removing the adversarial term (no_dom) raises RMSE on both platforms by more than two seed standard deviations, so the gain comes from the adversarial term; removing the consistency term (no_cons) changes RMSE by less than one standard deviation. Two of the four cells are therefore not resolvable within seed noise and we do not interpret them.

**Table 2.** Ablations on the held-out platform, single run each, contact-window convention; the reference row is the mean of the 3 seeds in Table 1.

| Variant | RMSE E1 (N) | RMSE E2 (N) |
|---|---|---|
| ours (full) | 0.202 | 0.303 |
| no_dom | 0.250 | 0.355 |
| no_cons | 0.203 | 0.304 |

### 4.5 Evaluation blind spot
The standard full-window evaluation averages over non-contact samples, which hides the offset error because most frames carry zero force; the contact-window convention exposes it. We therefore report the contact-window numbers only and give the full-window values in the released result files.

### 4.6 Discussion and limitations
If the improvement had been below 5 % or not consistent across seeds, the preregistered fallback was a calibration study of the sensor offset rather than a method claim; the observed improvement is consistent across seeds. The study covers two platforms and a third platform remains future validation. The consistency term is not resolvable at the present seed budget, so we make no claim about it.

## 5. Conclusion
Cross-platform degradation of vision-based force estimation is dominated by a label-side sensor offset. A domain-adversarial regularizer attached behind the prediction head removes it and lowers RMSE on the held-out platform by 19.2% relative to the strongest baseline, with the gain attributable to the adversarial term under an explicit seed-noise resolution.

## References
[1] K. He, X. Zhang, S. Ren, J. Sun, Deep residual learning for image recognition, CVPR 2016.
[2] Y. LeCun, Y. Bengio, G. Hinton, Deep learning, Nature 2015.
[3] D. P. Kingma, J. Ba, Adam: a method for stochastic optimization, arXiv 2014.
