### Unified Fine-Tuning: Dataset and Training Procedure

**Summary:** The unified model trains a single LoRA adapter to handle all three analysis tasks — incident summarization (Task S), cause analysis (Task A), and risk assessment (Task B) — from one GGUF file. It uses a purpose-built dataset pipeline (5 dedicated scripts) that intersects the summarization and risk source datasets, then augments with risk-only incidents to address task dilution. The production model (v2) trains on 2195 records with lora_r=128 + RSLoRA. A v3 upsampling experiment was abandoned after it degraded performance on both tasks.

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

| Dataset | Records | Description |
|---------|---------|-------------|
| `summarization_dataset_v4.json` | 961 | Summary LLM responses (GPT-4o, GPT-4o-mini, Qwen2.5 1.5B, Qwen2.5 3B) |
| `risk_dataset_v2.json` | 826 | Cause+risk LLM responses + dag_analysis |
| `summarization_results_merged.json` | 802 | Summary judge scores (gpt-oss-120b) |
| `risk_dataset_v2_results_qwen35.json` | 826 | Cause+risk judge scores (Qwen3.5, subscored) |

The unified dataset requires every incident to have both summary and risk judge scores — a stricter requirement than either standalone pipeline. Only the 802 incidents scored on both tasks qualify. The final augmented training set (v2) contains **2195 SFT records** across all three task types.

For how the source datasets were generated, see [Summarization Dataset Report](DATASET_REPORT.md) and [Risk Analysis Dataset Report](DATASET_RISK_REPORT.md).

---

### Step 1 — Merge Summary Judge Results

[`merge_summary_results.py`](https://github.com/stratosphereips/Slips-tools/blob/main/alert_summary/merge_summary_results.py) merges judge results from two evaluation runs:

- `summarization_dataset_v3_results_oss.json` (532 incidents, gpt-oss-120b via e-infra.cz)
- `summarization_v4_new_results_oss.json` (270 new v4 incidents, gpt-oss-120b via NVIDIA NIM)

**Output:** `summarization_results_merged.json` — 802 incidents with summary judge scores.

---

### Step 2 — Build Unified Dataset

[`build_unified_dataset.py`](https://github.com/stratosphereips/Slips-tools/blob/main/alert_summary/build_unified_dataset.py) joins all four source datasets on `incident_id`, keeping only the 802 incidents scored on both tasks:

- Identity fields + timeline from `summarization_dataset_v4.json`
- `dag_analysis` from `risk_dataset_v2.json` (full coverage for all 802)
- Summary LLM responses (4 models) from `summarization_dataset_v4.json`
- Cause+risk LLM responses (4 models) from `risk_dataset_v2.json`
- Summary judge scores from `summarization_results_merged.json`
- Cause+risk subscored judge scores from `risk_dataset_v2_results_qwen35.json`

**Output:** `datasets/unified_dataset.json` — 802 incidents.

---

### Step 3 — Filter Dataset

[`filter_dataset_unified.py`](https://github.com/stratosphereips/Slips-tools/blob/main/alert_summary/filter_dataset_unified.py) applies quality thresholds from both standalone pipelines simultaneously — an incident must pass all filters to be retained:

| Filter | Threshold |
|--------|-----------|
| Best summary score | ≥ 4 / 10 |
| Best cause total | ≥ 14 / 30 |
| Best risk total | ≥ 10 / 30 |
| Summary response token length | 50–400 tokens |
| Cause response token length | 50–600 tokens |
| Risk response token length | 30–300 tokens |
| Risk level keyword | Critical / High / Medium / Low |

**Result:** 750 / 802 incidents passed (93.5%). Split 90/10 (seed=42): **675 train / 75 eval**.

---

### Step 4 — Select Best Responses

[`select_best_responses_unified.py`](https://github.com/stratosphereips/Slips-tools/blob/main/alert_summary/select_best_responses_unified.py) selects the highest-scoring model response per task per incident and builds SFT conversation records:

- **Task S**: best summary score (1–10) → `[system, user(dag), assistant(summary)]`
- **Task A**: best cause total (subscored) → `[user(cause_prompt+dag), assistant(cause_analysis)]`
- **Task B**: same winner as Task A → `[user(risk_prompt+dag), assistant(risk_assessment)]`

DAG inputs are truncated at 3500 tokens at clean line boundaries with an explicit truncation marker. Records are interleaved S→A→B per incident so the adapter sees all three task types continuously throughout training.

**Output:** `unified_train_dataset.json` — 2025 train records (675 × 3 tasks), 225 eval records.

The three task types use distinct prompt formats:

| Task | Prompt focus | Output structure |
|---|---|---|
| **Task S** (Summarization) | Human-readable incident summary | Summary + Key Events + Threat Assessment |
| **Task A** (Cause Analysis) | Structured root cause identification | Possible Causes × 3 categories + Conclusion |
| **Task B** (Risk Assessment) | Calibrated risk evaluation | Risk Level + Justification + Business Impact + Likelihood + Priority |

---

### Step 5 — Augment with Risk-Only Incidents (v2)

After v1 evaluation, a performance gap was found between the unified model and the standalone risk model on cause analysis. The root cause was task dilution: the unified pipeline's intersection requirement (both summary and risk scores) excluded 85 risk-only incidents that passed the standalone risk quality filter.

[`augment_unified_with_risk.py`](https://github.com/stratosphereips/Slips-tools/blob/main/unsloth-scripts/augment_unified_with_risk.py) appends cause+risk SFT records for those 85 additional incidents to `unified_train_dataset.json`, using the same DAG truncation logic (3500 tokens).

**Output:** `unified_train_dataset_augmented.json` — **2195 train records** (678 summary + 1518 cause + 1519 risk after deduplication rounding).

This is the dataset used to train the production model (v2).

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

| Version | Dataset | lora_r | Epochs | Key Change | Outcome |
|---------|---------|--------|--------|------------|---------|
| v1 | `unified_train_dataset.json` (2025 records) | 64 | 3 | Initial 3-task unified training | Weak risk performance vs standalone |
| **v2** | `unified_train_dataset_augmented.json` (2195 records) | **128** | **2** | +85 risk-only incidents; higher rank; fewer epochs | **Production model** |
| v3 | `unified_train_dataset_augmented_2x_risk.json` | 128 | 2 | 2× upsampling of cause+risk records | Abandoned — summary −6.4pp, risk −13.5pp vs v2 |

**v1 → v2:** The v1 model showed a performance gap on risk/cause tasks vs the standalone risk model. Root cause: task dilution — summary, cause, and risk share the same adapter parameters at r=64. Fix: raise lora_r to 128 (more capacity for three competing tasks) + add 85 risk-only incidents excluded by the intersection requirement + reduce to 2 epochs to avoid overfitting toward the most frequent task pattern (summary).

**v3 post-mortem:** Doubling the already-dominant cause+risk records intensified training imbalance. The model overfit to the repeated pattern rather than generalizing better. v2, which reaches 81.8% cause+risk naturally from dataset sizes, is the better-calibrated training distribution.

---

### Published Model

The trained model (v2) is published on HuggingFace:

> **[stratosphere/qwen2.5-1.5b-slips-immune-unified](https://huggingface.co/stratosphere/qwen2.5-1.5b-slips-immune-unified)**

For evaluation results, see [Unified Fine-Tuned Model: Evaluation Results](finetuning_unified_results.md).  
For GGUF conversion and Ollama deployment, see [Quantization and Deployment](finetuning_quantization.md).
