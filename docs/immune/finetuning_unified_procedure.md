### Unified Fine-Tuning: Dataset and Training Procedure

**Summary:** The unified model trains a single LoRA adapter to handle all three analysis tasks — incident summarization (Task S), cause analysis (Task A), and risk assessment (Task B) — from one GGUF file. It uses a merged and augmented dataset of 3715 records with lora_r=128 + RSLoRA to accommodate the wider task objective. Version 2 (v2) is the production model; a v3 upsampling experiment was abandoned after it degraded performance on both tasks.

---

### Index
- [Motivation](#motivation)
- [Dataset](#dataset)
- [Step 1 — Quality Filtering and Merging](#step-1--quality-filtering-and-merging)
- [Step 2 — Ground Truth Selection](#step-2--ground-truth-selection)
- [Training](#training)
- [Version History](#version-history)
- [Published Model](#published-model)

---

### Motivation

Running two separate models on the Raspberry Pi 5 — one for summarization, one for cause+risk — requires loading and unloading GGUF files between tasks, adding memory and latency overhead. A unified adapter handles all three tasks from a single model file, eliminating model-switching at deployment time.

The trade-off is a harder training objective: one adapter must learn three distinct output formats and reasoning patterns simultaneously. This requires a higher LoRA rank than either standalone model.

---

### Dataset

**Source datasets:**
- Summarization: `unified_train_dataset_augmented.json` — merged from summarization and risk datasets, with augmented incident variations
- The combined dataset contains **3715 records**: 678 summary (18.2%), 1518 cause (40.9%), 1519 risk (40.9%)

The summarization records are a minority by design — the source summarization dataset (532 incidents) is smaller than the risk dataset (826 incidents), and both tasks require equal cause/risk representation. The 81.8% cause+risk proportion reflects the relative dataset sizes, not deliberate weighting.

For how the source datasets were generated, see [Summarization Dataset Report](DATASET_REPORT.md) and [Risk Analysis Dataset Report](DATASET_RISK_REPORT.md).

---

### Step 1 — Quality Filtering and Merging

The unified dataset is built by merging the quality-filtered outputs from both standalone pipelines:

- Summarization records: produced by [`filter_dataset.py`](https://github.com/stratosphereips/Slips-tools/blob/main/unsloth-scripts/filter_dataset.py) + [`select_best_responses.py`](https://github.com/stratosphereips/Slips-tools/blob/main/unsloth-scripts/select_best_responses.py) — same filters as the standalone summarization model (score ≥ 4, tokens 50–400)
- Cause + risk records: produced by [`filter_dataset_risk.py`](https://github.com/stratosphereips/Slips-tools/blob/main/unsloth-scripts/filter_dataset_risk.py) + [`select_best_responses_risk.py`](https://github.com/stratosphereips/Slips-tools/blob/main/unsloth-scripts/select_best_responses_risk.py) — same filters as the standalone risk model (cause score ≥ 14, risk score ≥ 10, token length checks)

The merged and augmented combined dataset is [`unified_train_dataset_augmented.json`](https://github.com/stratosphereips/Slips-tools/blob/main/unsloth-scripts/unified_train_dataset_augmented.json).

---

### Step 2 — Ground Truth Selection

Each record in the unified dataset is a two-turn SFT conversation:

- `user` — single message containing the task instructions (security analyst persona, task description, output format rules) and the DAG analysis text
- `assistant` — the best-scoring model response for that task type (ground truth)

The three task types use distinct system prompts that define the expected output structure:

| Task | Prompt focus | Output structure |
|---|---|---|
| **Task S** (Summarization) | Human-readable incident summary | Summary + Key Events + Threat Assessment |
| **Task A** (Cause Analysis) | Structured root cause identification | Possible Causes × 3 categories + Conclusion |
| **Task B** (Risk Assessment) | Calibrated risk evaluation | Risk Level + Justification + Business Impact + Likelihood + Priority |

All three task types are interleaved in the combined dataset so the adapter sees each task type throughout every training epoch, preventing catastrophic forgetting across tasks.

DAG inputs exceeding the token budget are truncated at 3500 tokens at a clean line boundary.

---

### Training

Training follows the general procedure in [Fine-Tuning Approach](finetuning_procedure.md). Unified-specific config values:

| Parameter | Value |
|---|---|
| Max sequence length | 4096 |
| LoRA rank (`r`) | 128 |
| LoRA alpha | 128 |
| LoRA dropout | 0.0 |
| RSLoRA | enabled (required at r=128) |
| LoRA targets | q_proj, k_proj, v_proj, o_proj, gate_proj, up_proj, down_proj |
| Epochs | 2 |
| Learning rate | 2e-5 |
| LR scheduler | cosine |
| Warmup steps | 20 |
| Weight decay | 0.01 |
| Batch size (effective) | 16 (2 × grad accum 8) |
| Optimizer | adamw_8bit |
| Precision | BF16 |
| Quantization (training) | 4bit (QLoRA) |
| Hardware | A100 80GB MiG 20GB slice (e-infra.cz cloud) |

The higher LoRA rank (r=128 vs r=16 for summarization, r=64 for risk) is necessary to accommodate three distinct task objectives. RSLoRA normalizes the adapter contribution at higher ranks to prevent training instability.

```bash
python3 train_qwen.py --config config_unified_4096_20gb.yaml
# Reads config, outputs merged 16-bit weights
```

---

### Version History

| Version | Dataset | Key Change | Outcome |
|---------|---------|------------|---------|
| v1 | `unified_train_dataset.json` | Initial 3-task unified training | Published as baseline |
| **v2** | `unified_train_dataset_augmented.json` (3715 records) | Augmented with incident variations; 2 epochs | **Production model** |
| v3 | `unified_train_dataset_augmented_2x_risk.json` | 2× upsampling of cause+risk records (81.8% → ~90%) | Abandoned — summary −6.4pp, risk −13.5pp vs v2 |

**v3 post-mortem:** Doubling the already-dominant cause+risk records intensified training imbalance. The model overfit to the repeated pattern rather than generalizing better. v2, which reaches the same 81.8% cause+risk proportion naturally from dataset sizes, is the better-calibrated training distribution.

---

### Published Model

The trained model (v2) is published on HuggingFace:

> **[stratosphere/qwen2.5-1.5b-slips-immune-unified](https://huggingface.co/stratosphere/qwen2.5-1.5b-slips-immune-unified)**

For evaluation results, see [Unified Fine-Tuned Model: Evaluation Results](finetuning_unified_results.md).  
For GGUF conversion and Ollama deployment, see [Quantization and Deployment](finetuning_quantization.md).
