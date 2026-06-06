# Hybrid AlertBERT + Qwen Summary

- Python: `/home/lhq/miniconda3/envs/dl/bin/python`
- CUDA available: `True`, devices: `8`
- Selected AlertBERT params: `delta=8.0`, `theta=256.0`

## Metrics

| Method | Precision | Recall | TNR | F1 |
|---|---:|---:|---:|---:|
| TimeDelta | 0.2258 | 0.9475 | 0.5579 | 0.2374 |
| AlertBERT | 0.3419 | 0.6021 | 0.9936 | 0.2225 |
| Hybrid triage | 0.8631 | 1.0000 | n/a | 0.9265 |

## Cost

- LLM clusters: `20` / `9440` (0.21%)
- Prompt tokens: `4065`, output tokens: `997`
- Pure cluster-level LLM token estimate: `2389264.0`
