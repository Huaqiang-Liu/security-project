# 题目与要求
交付
1. 综合研究与设计报告：主要包含背景调研、方案设计、实验分析、安全评估、创新性分析及组内分工。
2. 相关验证代码/脚本：结合开源库实现的Demo、自动化测试脚本或攻击模拟脚本，能跑通证明原理论证即可。

第12周（5月19日）进行开题汇报（口头简述即可，每组不超过3分钟）；
第15周（6月9日）开展成果汇报（每组约10-15min报告+5min提问）；
6月15日前将相关材料发送至助教邮箱：zhengzhoum@stu.pku.edu.cn 【邮件主题为 网络和信息安全课程项目+E3A+csn lhq】，形成一个压缩包。

题目
E3. 基于AI的安全运营自动化与威胁情报提取 (CTI) 
背景：安全运营中心（SOC）每天会收到海量的告警日志，安全分析师（Tier 1）疲于奔命（告警疲劳）。同时，互联网上每天产生大量非结构化的安全威胁情报（博客、推特、安全报告）。
任务： 
1. 调研AI技术如何在安全运营的“告警降噪”、“事件分诊（Triage）”或“威胁情报提取”中发挥作用。
2. 方向A（告警降噪）：构造一组混杂了真实攻击与误报的Web访问日志，利用聚类算法或LLM，实现对高危事件的自动化标记与归类。
3. 在报告中展示数据处理与提炼的流程图，论证这种AI辅助手段能够为安全运营团队节省多少时间成本，并探讨AI判断错误的容错机制。


# 报告正文

## 1. 背景调研
安全运营中心（SOC）的分析师（Tier 1）每天需要处理海量的安全告警日志（如 WAF、IDS、EDR 告警）。在这些海量告警中，绝大多数（通常超过 90%）是误报（False Positives）或无明显威胁的低危事件。大量的冗余告警导致了严重的“告警疲劳”（Alert Fatigue），使得安全人员容易在噪音中忽略真正的针对性攻击。
现有的机器学习方案（如孤立森林、SVM或小型的深度学习模型）能够高效地进行初步的异常检测与聚类，但它们缺乏对复杂上下文和业务逻辑的深度理解，容易在模糊边界（Grey Area）产生较高的误报率。
另一方面，大语言模型（LLMs）在自然语言理解和逻辑推理上展现了惊人的能力，在处理复杂的网络攻击行为分析时，能够提取潜在的威胁情报（CTI）并作出准确研判。然而，让 LLM 处理所有的原始日志会消耗庞大的计算资源与巨额的 Token 成本，在实时海量日志场景下极不现实。
因此，我们需要一种能够在成本与准确率之间取得最佳平衡的架构。

## 2. 方案设计
本项目提出一种“大小模型协同 (Small-Model Baseline + LLM On-Demand)”的架构：
1. 轻量级基线降噪 (Small-Model Baseline)：
   - 采用 AlertBERT (基于 Masked Language Model 预训练的轻量级日志模型) 作为第一层防御。
   - AlertBERT 能够在大规模、高并发的日志中提取语义 Embedding，并通过层次聚类（Agglomerative Clustering）将高度相似的常规告警及明显攻击快速聚集归类，实现超过 90% 的初始降噪。
2. LLM 按需分诊 (LLM On-Demand Triage)：
   - 在 AlertBERT 的聚类过程中，我们将引入置信度（Confidence）或不确定度（Uncertainty）衡量标准（例如：告警向量到所属簇中心的距离，或孤立点得分）。
   - 针对低置信度、无法被轻量级模型准确分类的“边界告警”事件，触发大语言模型（本地部署的 Qwen-3-8B）进行深入推理。
   - LLM 接收被格式化（Prompt Engineering）的告警上下文，判断其是否为多阶段攻击的组成部分，或者纯属环境噪音。

该架构的优势在于，利用计算开销极低的小模型处理海量确定性任务，将稀缺且昂贵的 LLM 算力聚焦于少数疑难、复杂的威胁判定上。

## 3. 实验设计
为了验证上述协同方案的有效性，我们将基于 AIT-ADS (AIT Alert Dataset) 进行对比实验。实验将分为以下几个阶段：
1. 数据准备与注入：
   - 基于 AIT-ADS 的告警数据集和 `labels.csv` 进行数据预处理，构建混杂了各类攻击和大量误报（Noise）的网络日志序列。
   - 使用原作者的增强脚本生成并发攻击场景（AIT-ADS-A）。
2. 基线模型评估 (Baseline Evaluation)：
   - 加载仓库中已经训练好的 AlertBERT 模型，在复杂并发攻击场景下评估其聚类与分诊能力，记录 ARI、NMI 和 F1-score 等聚类指标。
3. 大小模型协同评估 (Hybrid Approach Evaluation)：
   - 结合 AlertBERT 的特征距离指标，提取 Top-N% 难以确定的告警。
   - 调用本地 Qwen-3-8B 进行研判分类。
   - 对比 AlertBERT + LLM 与纯 AlertBERT 在聚类准确性上的提升，并重点统计 LLM 调用的 Token 消耗量，绘制“准确率 vs. Token 开销”的权衡曲线，证明在极低的 Token 成本下可获得研判能力的显著提升。

本方法流程图见图1。
![Flow Chart](experiments/assets/fig1_flowchart.png)


## 4. 实验操作流程与代码说明
实验脚本 `experiments/hybrid_alertbert_qwen.py`直接复用 AlertBERT 代码、AIT-ADS-A 增强数据和本地 Qwen3-8B 权重，形成可执行的端到端 Demo。

### 4.1 实验环境
开发与测试过程中，代码运行在 conda 环境中，使用 `AlertBERT/requirements.txt` 进行初始化。机器可见 8 张 NVIDIA RTX A6000，驱动版本 550.163.01，CUDA 12.4，`torch` 版本为 `2.6.0+cu124`。

脚本提供环境检查入口：

```bash
python experiments/hybrid_alertbert_qwen.py verify-env \
  --output-dir outputs/env_check
```

该命令会检查 CUDA、GPU 数量、`graph_tool`、AlertBERT 目录和 Qwen3-8B 权重路径，并将结果写入 `outputs/env_check/env.json`。

### 4.2 数据与基线
实验使用 `AlertBERT/aitads_augmented/configs/simul-attacks.json` 对应的 AIT-ADS-A 并发攻击配置。该配置把不同 AIT-ADS 场景中的攻击和噪声重新组合，用于测试模型在高噪声和攻击重叠情况下的告警分组能力。

ait_ads数据集应该解压在`data/`中，即`labels.csv`的路径为`data/ait_ads/labels.csv`

对比方法包括三组：

1. TimeDelta baseline：只根据相邻告警时间间隔聚类，是 AlertBERT 论文中使用的传统基线。
2. AlertBERT baseline：加载 `AlertBERT/saved_models/mlm_1l_2h_16d_simul-attacks_1_60k`，使用 MLM embedding 和时间-余弦距离进行告警聚类。
3. Hybrid AlertBERT + Qwen：先用 AlertBERT 聚类，再对低置信度簇调用本地 Qwen3-8B，输出 `attack/benign/uncertain` 和攻击类型。

为了保证稳定性，脚本默认使用 `scipy` 计算连通分量，而不是 AlertBERT 原实现默认的 `graph_tool`。原因是本地环境中 `graph_tool` 可以导入，但在 AlertBERT 聚类阶段对部分参数组合会触发进程级异常；`scipy` 速度较慢但更可复现。若希望尝试原实现路径，可以传入 `--component-library graph-tools`。

### 4.3 参数选择与运行命令
完整实验默认在 validation split 上选择 AlertBERT 参数，再在 test split 上报告结果。搜索网格为：

- `delta = [8, 12, 16, 24]`
- `theta = [32, 64, 128, 256]`
- 只保留 `theta >= delta` 的组合

完整实验命令：

```bash
python experiments/hybrid_alertbert_qwen.py run \
  --config simul-attacks \
  --tune-split val \
  --eval-split test \
  --model-id mlm_1l_2h_16d_simul-attacks_1_60k \
  --llm-mode qwen \
  --model-path pretrained_models/Qwen3-8B \
  --component-library scipy \
  --output-dir outputs/hybrid_alertbert_qwen
```

> 实验运行时，日志中的 `RuntimeWarning: Mean of empty slice` 和 `Degrees of freedom <= 0 for slice` 来自 AlertBERT 原评估函数在计算分层 macro 指标时，对某些在当前 split 或当前 scenario 中不存在的攻击标签执行 `nanmean/nanstd`。由于 AIT-ADS-A 的攻击标签分布是不均匀的，并不是每个攻击阶段都会出现在每个场景中，所以这些空切片 warning 是预期现象。

### 4.4 低置信度簇筛选
Hybrid 方法的关键不是把全部告警交给 LLM，而是只挑出 AlertBERT 难以确定的簇。脚本为每个簇计算不确定度分数，特征包括：

- 簇内告警 embedding 到簇中心的平均余弦相似度，越低越不确定；
- 簇大小，单点簇更不确定；
- `host` 熵和 `short` 熵，簇内主机或告警类型越混杂越不确定；
- 簇内时间跨度，跨度越大越可能需要复核。

默认选择不确定度最高的 5% 簇，且最多 20 个簇交给 Qwen3-8B。所有阈值均可通过命令行参数调整：`--uncertain-top-pct`、`--max-llm-clusters`、`--alerts-per-cluster`。

### 4.5 Qwen 分诊与输出格式
Qwen3-8B 的 prompt 输入为簇内最多 20 条代表性告警，字段包括 `raw_time`、`name`、`short`、`host` 和 `ip`。模型必须返回 JSON：

```json
{
  "decision": "attack|benign|uncertain",
  "attack_type": "service_scan|dirb|wpscan|webshell_cmd|crack_passwords|privilege_escalation|dnsteal|unknown|none",
  "confidence": 0.0,
  "rationale": "short reason"
}
```

脚本会校验 JSON、类别和值域。如果 Qwen 输出无法解析、置信度低于 0.7，或攻击类型不在允许列表中，则该簇统一标记为 `uncertain`，不会自动丢弃，而是进入人工复核队列。这一点体现了安全运营中的容错原则：AI 可以帮助排序和降噪，但不能在高风险场景中无约束替代分析师。

### 4.6 指标与结果文件
实验输出目录中的主要文件含义如下：

- `env.json`：Python、CUDA、GPU、`graph_tool`、Qwen 路径等环境信息；
- `tuning_results.csv`：AlertBERT 参数搜索结果；
- `timedelta_test_metrics.json`：TimeDelta baseline 的 macro precision、recall、TNR、F1；
- `alertbert_test_metrics.json`：AlertBERT 的 ARI、NMI、homogeneity、completeness、pairwise F1 和 macro 指标；
- `cluster_uncertainty.csv`：每个簇的不确定度、簇大小、真实攻击比例等；
- `qwen_decisions.jsonl`：Qwen 或规则分诊对低置信度簇的输出；
- `hybrid_metrics.json`：Hybrid 的攻击识别 precision、recall、F1、LLM 调用比例、Token 消耗和纯 LLM 成本估计；
- `summary.md`：结果摘要表。

画图脚本 `experiments/plot_experiment_assets.py` 会从实验输出目录读取 `clusters.csv`、`cluster_uncertainty.csv`、`hybrid_metrics.json`、`qwen_decisions.jsonl` 等文件，并生成可视化结果。

```bash
python experiments/plot_experiment_assets.py \
  --results-dir outputs/hybrid_alertbert_qwen \
  --asset-dir experiments/assets
```

我们将比较三点：AlertBERT 相比 TimeDelta 是否提升了攻击告警聚类质量；Hybrid 是否只用很小比例的 Qwen 调用覆盖低置信度簇；按需调用与“所有告警直接交给 LLM”的 Token 成本差距。

### 4.7 实验结果

测试集共包含 499257 条告警，其中攻击告警 430880 条，噪声/误报告警 68377 条。AlertBERT 将这些告警聚为 9440 个簇，平均每簇约 52.9 条告警。也就是说，在进入人工分析前，系统已经把逐条告警视角压缩为簇视角，这是本项目最直接的降噪收益。

![AIT-ADS attack phase matrix](experiments/assets/fig2_attack_phase_matrix.png)

图 2 展示了 AIT-ADS 中不同场景和攻击阶段的覆盖情况。可以看到，数据集不是单一攻击样本，而是包含扫描、目录爆破、WordPress 扫描、Webshell、口令破解、权限提升、DNS 数据外传等多个攻击阶段。这支持本项目使用该数据集作为“真实攻击与误报混杂”的实验基础。

![Cluster overview](experiments/assets/fig3_cluster_overview.png)

图 3 展示了正式测试集中的告警组成和 AlertBERT 聚类后的最大簇规模。正式结果中攻击告警占比较高，主要原因是 test split 中 `dirb` 阶段告警数量极大，约 414858 条。这说明 AIT-ADS-A 的类别分布高度不均衡，评估时不能只看总体准确率，而应同时观察 precision、recall、TNR 和聚类压缩效果。

![Uncertainty distribution](experiments/assets/fig4_uncertainty_distribution.png)

图 4 展示了簇级不确定度分布。红色虚线表示默认的 Top 5% handoff 阈值。测试中设置 `--max-llm-clusters 20`，所以最终只有 20 个簇进入 Qwen3-8B 分诊。相对于全部 9440 个簇，LLM 处理比例仅为 0.21%。这说明该系统没有把大模型当作全量处理器，而是作为低置信度样本的按需分诊器。

![Cluster size vs uncertainty](experiments/assets/fig5_cluster_size_vs_uncertainty.png)

图 5 展示簇大小与不确定度之间的关系。正式实验中，被 Qwen 选中的 20 个低置信度簇全部是单点簇，其中 19 个是噪声或误报，1 个是真实攻击告警。这说明当前不确定度策略能较好地找到“AlertBERT 难以归并的孤立点”，但也暴露了一个安全边界：孤立攻击告警可能缺少上下文，Qwen 容易把它解释为普通运维异常。因此，实际部署中不应直接丢弃 Qwen 判为 benign 的高不确定度单点告警，而应将其放入低优先级复核队列。

![Metric comparison](experiments/assets/fig6_metric_comparison.png)

图 6 汇总了 TimeDelta、AlertBERT 和 Hybrid triage 的关键指标。TimeDelta 的 recall 为 0.9475，说明它倾向于把相关攻击告警合并在一起；但 precision 只有 0.2258，TNR 为 0.5579，说明它也会把大量噪声混进攻击簇。AlertBERT 的 precision 提升到 0.3419，TNR 提升到 0.9936，表明语义聚类显著降低了误合并噪声的风险；代价是 recall 降到 0.6021，macro F1 为 0.2225，略低于 TimeDelta 的 0.2374。因此，AlertBERT 并不是在所有指标上压倒 TimeDelta，而是提供了更保守、更高精度、更强噪声隔离的聚类结果。

Hybrid triage 的攻击识别 precision 为 0.8631，recall 接近 1.0，F1 为 0.9265。这里的高 recall 来自安全优先策略：除高置信度 benign 外，其余 `attack`、`uncertain` 和普通 review 簇都保留给分析师，因此几乎不会漏掉攻击。正式结果中 false negative 为 1，来源是一个真实攻击单点簇被 Qwen 判为 benign。这个结果说明方法总体达到了“低漏报、可解释、低成本分诊”的目标，但自动 benign 策略必须谨慎，尤其是单点告警不应直接彻底丢弃。

![Token cost](experiments/assets/fig7_token_cost.png)

图 7 展示按需 LLM 与纯 LLM 的 Token 成本对比。正式实验中，Qwen 只处理 20 个簇，输入 4065 tokens，输出 997 tokens，总计 5062 tokens。如果对全部 9440 个簇都做 cluster-level LLM 分诊，估算成本约为 2389264 tokens。按需调用仅占该估算成本的约 0.21%，节省约 99.79% 的 Token。这是本项目最清晰的工程收益：LLM 被限制在少量疑难簇上，成本随低置信度样本数增长，而不是随全量告警数增长。

![Qwen triage](experiments/assets/fig8_qwen_triage.png)

图 8 展示 Qwen 对低置信度簇的分诊输出。20 个簇中，18 个被判为 benign，2 个被判为 uncertain。Qwen 的解释大多指向 ClamAV 数据库更新、监控 CPU 指标异常、DNS 日志异常、HTTP method 频率异常等运维或低上下文告警。这说明 Qwen 能给出结构化分诊理由，也能把不确定 DNS 异常保守地保留为 uncertain。但其中 1 个真实攻击告警被解释为 CPU 指标异常并判为 benign，说明 LLM 在缺少上下文的单点告警上存在误判风险。

## 5 结论

第一，数据和流程满足课程项目要求，能够展示真实攻击与误报混杂场景下的 SOC 告警降噪。第二，AlertBERT 相比 TimeDelta 的主要优势是显著提高 precision 和 TNR，降低噪声误合并；但它不是在 F1 上全面优于 TimeDelta，因此报告中应强调 trade-off，而不是简单宣称 SOTA 全面胜出。第三，Hybrid 方法达到了“低成本调用 LLM”的预期：只处理 0.21% 的簇，节省约 99.79% 的 cluster-level LLM Token 成本，同时保持接近 1.0 的攻击召回。第四，Qwen 的分诊解释有实际价值，但本次实验出现 1 个 false negative，说明高不确定度单点告警即使被判 benign，也更适合作为低优先级复核，而不是自动丢弃。

# 杂项
## 安全评估
本方案的安全风险主要来自三类错误：误把真实攻击判为 benign、误把噪声判为 attack 导致分析师负担没有下降、以及 Qwen 输出格式错误或解释不可靠。为降低风险，实验脚本采用保守策略：低置信度簇只允许被标记为 `attack`、`benign` 或 `uncertain`；低置信度、JSON 解析失败和低置信度输出全部进入 `uncertain`；`uncertain` 和 `attack` 都保留给分析师复核。也就是说，LLM 的主要作用是帮助排序和解释，而不是直接执行自动封禁、删除或忽略高危事件。
TODO：我也不知道这个“安全评估”应该写什么，现在这个仅用作占位


## 时效性与对比维度说明
1. 时效性：本方案没有采用老旧的机器学习算法（如传统的孤立森林、SVM），而是直接采用了前沿的无监督掩码语言模型（AlertBERT，代表领域最新 SOTA 进展）与最新的小型开源LLM（Qwen-3-8B，代表最新的生成式 AI 推理能力）。两者均为当前最具时效性的新工作/新技术。
2. 与现有工作对比 (Comparison with Existing Work)：
   本项目的实验将形成严谨的三维对比：
   - vs. 现有最先进的小模型工作 (SOTA Baseline)：以纯 AlertBERT 为基线，对比我们在引入 LLM 分诊后，对高难/模糊告警分类准确率的直接提升幅度。
   - vs. 现有直接使用大模型的暴力方案 (Pure LLM)：当前的另一类热门研究是直接让 LLM 吞噬所有日志。我们将通过统计我们“按需推理”架构的 Token 消耗，并在报告中量化对比“混合架构”与“纯大模型架构”在推理开销上的数量级差异，证明我们在实际工程与学术效益上的优越性。

## 组内分工
TODO: 待填充
