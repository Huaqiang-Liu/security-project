# Smoke Test 归档

本文件记录开发迭代阶段使用的 smoke test 命令和说明。Smoke test 只用于验证脚本通路、环境依赖、输出文件结构、Qwen 调用和 JSON 解析是否正常，不作为正式实验结果，也不应进入 `report.md` 的结论部分。

正式实验结果以 `outputs/hybrid_alertbert_qwen` 为准。

## 1. 无 Qwen 的快速通路测试

该命令只截取少量场景和告警，关闭 LLM 调用，用于验证 AlertBERT 聚类、TimeDelta baseline、低置信度簇筛选和结果文件写出是否能跑通。

```bash
python experiments/hybrid_alertbert_qwen.py run \
  --config simul-attacks \
  --eval-split test \
  --quick \
  --quick-delta 24 \
  --quick-theta 128 \
  --max-scenarios 1 \
  --max-alerts-per-scenario 2048 \
  --llm-mode off \
  --max-llm-clusters 1 \
  --device cuda:1 \
  --component-library scipy \
  --output-dir outputs/smoke_scipy
```

## 2. 带 Qwen 的快速通路测试

该命令用于验证本地 Qwen3-8B 能否被加载，低置信度簇是否能进入 prompt，模型输出是否能被解析为合法 JSON。由于 smoke test 样本很小，结果只说明调用链路可用，不能用于评价模型效果。

```bash
python experiments/hybrid_alertbert_qwen.py run \
  --config simul-attacks \
  --eval-split test \
  --quick \
  --quick-delta 24 \
  --quick-theta 256 \
  --max-scenarios 1 \
  --max-alerts-per-scenario 2048 \
  --llm-mode qwen \
  --model-path pretrained_models/Qwen3-8B \
  --max-llm-clusters 1 \
  --device cuda:1 \
  --component-library scipy \
  --output-dir outputs/smoke_qwen_256
```

## 3. Smoke Test 输出文件

正常跑通后，输出目录通常会包含以下文件：

- `env.json`：运行环境、CUDA、GPU、依赖库和模型路径信息；
- `timedelta_test_metrics.json`：TimeDelta baseline 指标；
- `alertbert_test_metrics.json`：AlertBERT 聚类指标；
- `clusters.csv`：AlertBERT 聚类后的告警明细；
- `cluster_uncertainty.csv`：簇级不确定度；
- `qwen_decisions.jsonl`：Qwen 或规则分诊结果；
- `hybrid_metrics.json`：Hybrid 分诊指标、Token 消耗和 LLM 调用比例；
- `summary.md`：本次运行的简要摘要。

## 4. 注意事项

Smoke test 会使用 `--quick`、`--max-scenarios` 和 `--max-alerts-per-scenario` 截断数据。截断后的样本可能缺少攻击标签或某些攻击阶段，因此部分 macro 指标可能为 `NaN`，AlertBERT 评估函数也可能输出 `RuntimeWarning: Mean of empty slice`。这类现象在 smoke test 中是预期的。

如果需要生成正式报告图表，应使用正式结果目录：

```bash
/home/lhq/miniconda3/envs/dl/bin/python experiments/plot_experiment_assets.py \
  --results-dir outputs/hybrid_alertbert_qwen \
  --asset-dir experiments/assets
```
