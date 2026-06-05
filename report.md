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

## 4. 实验操作流程与代码说明
实验脚本 `experiments/hybrid_alertbert_qwen.py`直接复用 AlertBERT 代码、AIT-ADS-A 增强数据和本地 Qwen3-8B 权重，形成可执行的端到端 Demo。

### 4.1 实验环境验证
开发与测试过程中，代码运行在 conda 环境中，使用 `AlertBERT/requirements.txt` 进行初始化。机器可见 8 张 NVIDIA RTX A6000，驱动版本 550.163.01，CUDA 12.4，`torch` 版本为 `2.6.0+cu124`。

脚本提供环境检查入口：

```bash
python experiments/hybrid_alertbert_qwen.py verify-env \
  --output-dir outputs/env_check
```

该命令会检查 CUDA、GPU 数量、`graph_tool`、AlertBERT 目录和 Qwen3-8B 权重路径，并将结果写入 `outputs/env_check/env.json`。实际验证中，沙箱外环境能够看到 8 张 A6000，且 `graph_tool` 可用。需要注意的是，`torch` 和 `graph_tool` 存在 `libgomp` 导入顺序冲突：若先导入 `torch` 再导入 `graph_tool`，可能出现 `GOMP_5.0` 符号缺失。实验脚本已经在任何 `torch` 导入前预加载 `graph_tool`，避免该问题。

### 4.2 数据与基线
实验使用 `AlertBERT/aitads_augmented/configs/simul-attacks.json` 对应的 AIT-ADS-A 并发攻击配置。该配置把不同 AIT-ADS 场景中的攻击和噪声重新组合，用于测试模型在高噪声和攻击重叠情况下的告警分组能力。

ait_ads数据集应该解压在`项目根目录/data`中，即`labels.csv`的路径为`data/ait_ads/labels.csv`

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

默认完整实验命令如下：

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

如果只需要验证脚本能跑通，可以运行截断版 smoke test：

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

该 smoke test 已经在本项目环境中跑通，并生成 `clusters.csv`、`cluster_uncertainty.csv`、`alertbert_test_metrics.json`、`timedelta_test_metrics.json`、`hybrid_metrics.json`、`qwen_decisions.jsonl` 和 `summary.md`。由于 smoke test 只截取每个场景开头的 2048 条告警，可能没有攻击标签，因此部分聚类指标会出现 `NaN`；这只用于验证代码通路，不作为最终实验结论。

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
- `summary.md`：可直接用于汇报的摘要表。

最终报告重点比较三点：第一，AlertBERT 相比 TimeDelta 是否提升了攻击告警聚类质量；第二，Hybrid 是否只用很小比例的 Qwen 调用覆盖低置信度簇；第三，按需调用与“所有告警直接交给 LLM”的 Token 成本差距。这样既回应了“与现有工作对比”的要求，也能说明本方案在工程上比纯 LLM 更可部署。

## 5. 安全评估
本方案的安全风险主要来自三类错误：误把真实攻击判为 benign、误把噪声判为 attack 导致分析师负担没有下降、以及 Qwen 输出格式错误或解释不可靠。为降低风险，实验脚本采用保守策略：低置信度簇只允许被标记为 `attack`、`benign` 或 `uncertain`；低置信度、JSON 解析失败和低置信度输出全部进入 `uncertain`；`uncertain` 和 `attack` 都保留给分析师复核。也就是说，LLM 的主要作用是帮助排序和解释，而不是直接执行自动封禁、删除或忽略高危事件。

## 6. 方案的学术先进性与对比维度
为了响应“时效性、新技术与现有工作对比”的核心要求，本方案在设计上具备以下考量：
1. 时效性与新技术 (Timeliness & New Tech)：
   - 本方案没有采用老旧的机器学习算法（如传统的孤立森林、SVM），而是直接采用了前沿的无监督掩码语言模型（AlertBERT，代表领域最新 SOTA 进展）与最新的开源大语言模型（Qwen-3-8B，代表最新的生成式 AI 推理能力）。两者均为当前最具时效性的新工作/新技术。
2. 与现有工作对比 (Comparison with Existing Work)：
   本项目的实验将形成严谨的三维对比：
   - vs. 现有最先进的小模型工作 (SOTA Baseline)：以纯 AlertBERT 为基线，对比我们在引入 LLM 分诊后，对高难/模糊告警分类准确率的直接提升幅度。
   - vs. 现有直接使用大模型的暴力方案 (Pure LLM)：当前的另一类热门研究是直接让 LLM 吞噬所有日志。我们将通过统计我们“按需推理”架构的 Token 消耗，并在报告中量化对比“混合架构”与“纯大模型架构”在推理开销上的数量级差异，证明我们在实际工程与学术效益上的优越性。

## 7. 项目展示讲稿（约 12 分钟）

### 7.1 数据是否符合作业要求
本项目当前使用的数据符合本课程 E3A 方向的核心要求。作业要求是“构造一组混杂了真实攻击与误报的 Web 访问日志，利用聚类算法或 LLM，实现对高危事件的自动化标记与归类”。我们使用的 AIT-ADS/AIT-ADS-A 不是原始 HTTP access log，而是 IDS/SOC 告警级日志：它已经经过检测系统抽取，包含告警名称、主机、IP、时间戳和攻击阶段标签。这个层级更接近 SOC Tier 1 分析师实际面对的告警队列，也与题目背景中“安全运营中心每天收到海量告警日志”的场景一致。

具体来说，AIT-ADS 包含多个真实攻击链场景和大量误报/噪声告警；AIT-ADS-A 进一步通过噪声增强和多场景混合构造了高噪声、攻击并发的告警流。因此，它满足“真实攻击与误报混杂”“需要自动标记与归类”“需要展示数据处理与提炼流程”的核心要求。需要在汇报中主动说明的边界是：我们的实验对象是 SOC 告警日志，而不是最原始的 Web 访问日志；这是因为本项目聚焦于告警降噪和分诊，而不是 IDS 规则本身的检测能力。

### 7.2 PPT 页 1：题目与核心问题（约 1 分钟）
大家好，我们组的项目题目是“基于 AI 的安全运营自动化与威胁情报提取”，我们选择的是其中的告警降噪方向。

这个问题来自安全运营中心，也就是 SOC 的日常工作。一个 SOC 每天可能会收到成千上万甚至更多告警，其中绝大多数并不是真正需要响应的攻击。Tier 1 分析师需要在这些告警里判断哪些是误报，哪些只是失败的攻击尝试，哪些是真正需要升级处理的高危事件。这个过程非常消耗人力，也容易造成告警疲劳。

所以我们的核心问题是：能不能用 AI 先把大量确定性告警自动聚类、压缩和排序，再只把少量模糊、困难的告警交给大模型做进一步分诊？换句话说，我们不是让大模型吞掉所有日志，而是让小模型和大模型各自处理自己擅长的部分。

### 7.3 PPT 页 2：为什么不能直接用 LLM 处理所有告警（约 1 分钟）
直觉上，大语言模型很适合做安全分析，因为它可以读懂告警描述，也能根据上下文解释攻击阶段。但是在 SOC 场景里，直接把每一条告警都交给 LLM 并不现实。

原因主要有三个。第一是成本问题，告警量非常大，逐条调用 LLM 会带来很高的 Token 消耗。第二是时延问题，SOC 分析需要及时响应，不能让所有告警都排队等待生成式模型推理。第三是可靠性问题，LLM 有时会输出格式错误、过度解释或产生不稳定结论，如果完全依赖它，反而会引入新的风险。

因此我们的设计目标不是“用 LLM 替代所有分析”，而是“用 LLM 处理最值得处理的少数疑难告警”。这也是后面混合架构的出发点。

### 7.4 PPT 页 3：数据集与任务适配性（约 1 分钟）
我们的实验数据基于 AIT-ADS，也就是 AIT Alert Dataset。它是一个真实感较强的 SOC 告警数据集，包含多个攻击场景，每个场景对应一条完整的多阶段攻击链，同时也包含大量 benign 或 false positive 告警。

为了更贴近真实 SOC 的复杂性，我们进一步使用 AlertBERT 项目中的 AIT-ADS-A 增强版本。AIT-ADS-A 做了两件事：第一是增加噪声比例，模拟真实环境中攻击告警远少于普通告警的情况；第二是把多个场景混合，让不同攻击在时间上交错出现，形成并发攻击场景。

这和作业要求中的“混杂真实攻击与误报”是一致的。唯一需要说明的是，我们处理的是 IDS/SOC 告警层日志，而不是原始 Web access log。这个选择更贴近安全运营中心的降噪和分诊任务，也更适合与 AlertBERT 这类现有工作比较。

### 7.5 PPT 页 4：现有工作与我们的定位（约 1.5 分钟）
在现有工作上，我们主要参考了三类方法。

第一类是传统的时间窗口方法，比如 TimeDelta。它的思想很简单：如果两个告警在时间上很接近，就认为它们可能属于同一事件。这类方法速度快、成本低，但是只看时间，不理解告警语义，所以在噪声高、攻击并发时容易把无关告警合并在一起。

第二类是自监督小模型，比如 AlertBERT。AlertBERT 会用 masked language modeling 学习告警字段的 embedding，再结合时间和语义距离做聚类。它比纯时间方法更强，也更适合冷启动场景，因为不需要大量人工历史标签。

第三类是 LLM 或多 Agent 方法。它们推理能力强，可以解释攻击意图和上下文，但成本和时延较高，不适合处理所有原始告警。

我们的定位是在第二类和第三类之间做协同：用 AlertBERT 做第一层大规模降噪，用 Qwen3-8B 只处理 AlertBERT 低置信度的簇。这样既保留小模型的效率，又利用 LLM 的推理能力。

### 7.6 PPT 页 5：系统设计（约 1.5 分钟）
我们的系统可以分成五步。

第一步是数据加载。脚本读取 AIT-ADS-A 的 `simul-attacks` 配置，构造包含攻击和噪声的告警流。

第二步是基线评估。我们同时运行 TimeDelta 和 AlertBERT，得到传统时间方法和小模型语义聚类方法的对比结果。

第三步是低置信度簇筛选。AlertBERT 聚类之后，每个簇会有一个不确定度分数。这个分数综合考虑簇内 embedding 到中心的相似度、簇大小、主机多样性、告警类型多样性和时间跨度。如果一个簇很小、很杂、相似度低，就说明小模型对它不够确定。

第四步是按需 Qwen 分诊。我们只把不确定度最高的少量簇交给本地 Qwen3-8B，让它输出 `attack`、`benign` 或 `uncertain`，同时给出攻击类型和简短理由。

第五步是结果汇总。脚本输出聚类指标、分诊指标、Token 消耗和纯 LLM 成本估计，用于说明混合架构的效果和节省。

### 7.7 PPT 页 6：实验代码与可复现流程（约 1 分钟）
我们新增的核心脚本是 `experiments/hybrid_alertbert_qwen.py`。这个脚本没有修改 AlertBERT 原代码，而是在外部复用它的数据集、模型加载和评估函数。

运行前可以先执行环境检查：

```bash
python experiments/hybrid_alertbert_qwen.py verify-env \
  --output-dir outputs/env_check
```

完整实验命令是：

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

我们也准备了 smoke test，用来快速验证代码链路。它只截取少量数据，所以不作为最终指标，只证明环境、AlertBERT 推理、低置信度筛选和 Qwen 调用能够跑通。

### 7.8 PPT 页 7：环境与实现细节（约 1 分钟）
实验运行在 `dl` conda 环境中，机器有 8 张 NVIDIA RTX A6000，CUDA 版本是 12.4，本地 Qwen3-8B 权重已经放在 `pretrained_models/Qwen3-8B`。

实现时有一个工程细节值得说明：AlertBERT 原实现依赖 `graph_tool` 做连通分量计算，而本地环境中 `torch` 和 `graph_tool` 有 `libgomp` 导入顺序冲突。我们在脚本里先预加载 `graph_tool`，再导入 `torch`，解决了这个问题。

另外，在实际聚类阶段，`graph_tool` 对部分参数组合会出现进程级异常。为了保证 Demo 稳定，我们默认使用 `scipy` 计算连通分量。这个选择速度可能慢一些，但更可复现，也符合课程项目“能跑通证明原理”的目标。

### 7.9 PPT 页 8：评价指标（约 1 分钟）
我们的评价分成两层。

第一层是聚类指标，用来比较 TimeDelta 和 AlertBERT，包括 ARI、NMI、homogeneity、completeness、pairwise precision、pairwise recall 和 pairwise F1。这些指标回答的问题是：模型是否把属于同一攻击阶段的告警聚在一起，同时避免把无关噪声混进来。

第二层是分诊指标，用来评价 Hybrid 策略，包括攻击识别 precision、recall、F1、自动判为 benign 的告警数、进入 LLM 的簇比例、输入输出 Token 数，以及如果所有簇都交给 LLM 的估算成本。

我们重点关注两个 trade-off：一是 AlertBERT 相比 TimeDelta 是否提高了聚类质量；二是 Hybrid 是否只用很小比例的 LLM 调用，就能处理最不确定的告警。

### 7.10 PPT 页 9：已验证的 Demo 结果（约 1 分钟）
目前我们已经完成了两个 smoke test。

第一个是不调用 Qwen 的 AlertBERT smoke test，输出目录是 `outputs/smoke_scipy`。它证明了环境检查、模型加载、TimeDelta baseline、AlertBERT 聚类、低置信度计算和结果导出都能跑通。

第二个是真实调用 Qwen 的 smoke test，输出目录是 `outputs/smoke_qwen_256`。在这个测试中，我们只把一个低置信度簇交给 Qwen。这个簇包含 14 条告警，真实攻击告警数为 0。Qwen 输出为 `benign`，攻击类型为 `none`，置信度为 0.95，理由是这些 TLS 和 Dovecot 登录成功类告警没有明显攻击迹象。

这次调用输入约 1130 tokens，输出约 66 tokens。虽然这是小规模测试，但它验证了三个关键点：本地 Qwen3-8B 能加载，模型输出能被 JSON 正确解析，低置信度簇可以通过 LLM 得到解释性分诊结论。

### 7.11 PPT 页 10：成本与节省逻辑（约 1 分钟）
我们项目最核心的价值不只是准确率，而是成本控制。

如果直接把所有告警或所有簇都交给 LLM，那么 Token 消耗会随着告警量线性增长。在 SOC 场景中，这个成本很快会变得不可接受。

Hybrid 策略的做法是，只处理不确定度最高的一小部分簇。脚本默认选择最高 5%，最多 20 个簇。这样 LLM 的调用比例被严格限制，成本是可控的。

在 smoke test 中，1 个簇的 Qwen 调用消耗约 1196 tokens。脚本同时估算了如果每个簇都调用 LLM 的成本，用来和按需调用做对比。正式实验中，我们会用 `hybrid_metrics.json` 里的 `llm_cluster_ratio` 和 `pure_llm_cluster_token_estimate` 展示这种节省。

### 7.12 PPT 页 11：安全容错机制（约 1 分钟）
在安全场景里，AI 判断错误的代价可能很高。因此我们没有设计成让 Qwen 直接自动处置告警，而是让它做辅助分诊。

具体容错机制有三点。

第一，Qwen 只能输出三类结果：`attack`、`benign` 和 `uncertain`。其中 `attack` 和 `uncertain` 都会保留给分析师复核。

第二，脚本会强制校验 JSON。如果输出格式错误、攻击类型不合法，或者置信度低于 0.7，就自动转成 `uncertain`。

第三，我们只让 Qwen 处理低置信度簇，不让它改变所有 AlertBERT 聚类结果。这样可以避免大模型单次错误扩大到全局系统。

所以，本项目中的 AI 是“帮助分析师排序和解释”，不是“完全替代分析师做最终决策”。

### 7.13 PPT 页 12：局限性与下一步（约 1 分钟）
这个项目目前还有几个局限。

第一，AIT-ADS 是告警级数据，不是最原始的 Web access log。如果要完全贴合“Web 访问日志”字面要求，下一步可以增加一层 WAF 或 Nginx access log 的模拟，再映射到告警层。

第二，目前 Hybrid v1 主要做分诊，不自动重写 AlertBERT 的聚类图。也就是说，Qwen 先帮助判断“这个簇是否值得分析师看”，后续可以扩展为“建议拆分或合并哪些簇”。

第三，完整实验需要跑完整的 `simul-attacks` validation/test split，并填入最终指标。现在的 smoke test 已证明通路可行，但不能替代最终定量结果。

下一步工作就是运行完整实验，把 `outputs/hybrid_alertbert_qwen/summary.md` 和各个 JSON 指标整理成 PPT 表格，并补充一两个 Qwen 分诊案例。

### 7.14 PPT 页 13：总结（约 0.5 分钟）
最后总结一下，我们的项目做了三件事。

第一，我们把课程要求中的“混杂真实攻击与误报的告警降噪”落到了 AIT-ADS-A 数据集上，并构造了可复现的实验流程。

第二，我们把现有工作 TimeDelta 和 AlertBERT 作为基线，说明为什么只看时间不够，以及为什么自监督小模型适合作为第一层降噪。

第三，我们引入本地 Qwen3-8B，只处理 AlertBERT 的低置信度簇，从而在成本可控的前提下提高分诊解释能力。

整体来看，这个项目展示的是一个更接近实际 SOC 的 AI 辅助工作流：小模型负责规模化处理，大模型负责疑难推理，最终高风险和不确定结果仍交给人类分析师确认。
