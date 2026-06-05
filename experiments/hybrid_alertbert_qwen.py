#!/usr/bin/env python3
"""Run AlertBERT + on-demand Qwen triage experiments on AIT-ADS-A.

This script is intentionally kept outside the vendored AlertBERT tree.  It
reuses AlertBERT data/model utilities, controls CUDA placement explicitly, and
exports compact artifacts for the course report.
"""

from __future__ import annotations

import argparse
import json
import math
import os
import re
import subprocess
import sys
import time
from collections import Counter, defaultdict
from dataclasses import dataclass
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd


ROOT = Path(__file__).resolve().parents[1]
ALERTBERT_DIR = ROOT / "AlertBERT"
DEFAULT_MODEL_ID = "mlm_1l_2h_16d_simul-attacks_1_60k"
DEFAULT_QWEN_PATH = ROOT / "pretrained_models" / "Qwen3-8B"


def import_torch():
    import torch

    return torch


def import_sklearn_metrics():
    from sklearn.metrics import (
        adjusted_rand_score,
        homogeneity_completeness_v_measure,
        normalized_mutual_info_score,
    )

    return adjusted_rand_score, normalized_mutual_info_score, homogeneity_completeness_v_measure


def import_alertbert():
    sys.path.insert(0, str(ALERTBERT_DIR))
    from alertbert.aitads import AITAlertDataset
    from alertbert.eval_grouping import eval_alert_grouping
    from alertbert.model_eval_utils import load_data_tools, load_ground_truth_label_vocabs, load_models, load_reports
    from alertbert.models import AlertBERT, MaskedLangModelInferenceWrapper, TimeDelta

    return {
        "AITAlertDataset": AITAlertDataset,
        "AlertBERT": AlertBERT,
        "MaskedLangModelInferenceWrapper": MaskedLangModelInferenceWrapper,
        "TimeDelta": TimeDelta,
        "eval_alert_grouping": eval_alert_grouping,
        "load_data_tools": load_data_tools,
        "load_ground_truth_label_vocabs": load_ground_truth_label_vocabs,
        "load_models": load_models,
        "load_reports": load_reports,
    }


def json_default(obj: Any) -> Any:
    if isinstance(obj, np.integer):
        return int(obj)
    if isinstance(obj, np.floating):
        return float(obj)
    if isinstance(obj, np.ndarray):
        return obj.tolist()
    if isinstance(obj, Path):
        return str(obj)
    return str(obj)


def write_json(path: Path, data: dict[str, Any]) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(json.dumps(data, indent=2, ensure_ascii=False, default=json_default) + "\n")


def run_cmd(args: list[str]) -> tuple[int, str]:
    try:
        proc = subprocess.run(args, check=False, text=True, stdout=subprocess.PIPE, stderr=subprocess.STDOUT)
        return proc.returncode, proc.stdout.strip()
    except FileNotFoundError as exc:
        return 127, str(exc)


def preload_graph_tool() -> str:
    """Import graph_tool before torch to avoid the libgomp symbol conflict."""
    try:
        import graph_tool  # noqa: F401

        return "ok"
    except Exception as exc:  # noqa: BLE001
        return f"failed: {exc}"


def verify_env(output_dir: Path | None = None) -> dict[str, Any]:
    graph_tool_status = preload_graph_tool()
    torch = import_torch()
    info: dict[str, Any] = {
        "python": sys.executable,
        "torch": getattr(torch, "__version__", None),
        "torch_cuda": getattr(torch.version, "cuda", None),
        "cuda_available": bool(torch.cuda.is_available()),
        "cuda_device_count": int(torch.cuda.device_count()) if torch.cuda.is_available() else 0,
        "qwen_path_exists": DEFAULT_QWEN_PATH.exists(),
        "alertbert_dir_exists": ALERTBERT_DIR.exists(),
    }
    if torch.cuda.is_available():
        info["cuda_devices"] = [
            {
                "index": i,
                "name": torch.cuda.get_device_name(i),
                "free_mem_mb": int(torch.cuda.mem_get_info(i)[0] // (1024 * 1024)),
                "total_mem_mb": int(torch.cuda.mem_get_info(i)[1] // (1024 * 1024)),
            }
            for i in range(torch.cuda.device_count())
        ]
    code, out = run_cmd(["nvidia-smi", "--query-gpu=index,name,memory.free,memory.total", "--format=csv,noheader,nounits"])
    info["nvidia_smi_code"] = code
    info["nvidia_smi_query"] = out
    info["graph_tool"] = graph_tool_status
    if output_dir:
        write_json(output_dir / "env.json", info)
    print(json.dumps(info, indent=2, ensure_ascii=False, default=json_default))
    return info


def select_device(requested: str) -> str:
    torch = import_torch()
    if requested != "auto":
        return requested
    if not torch.cuda.is_available():
        return "cpu"
    free = [(torch.cuda.mem_get_info(i)[0], i) for i in range(torch.cuda.device_count())]
    return f"cuda:{max(free)[1]}"


class DeviceCollate:
    def __init__(self, collate_fn: Any, device: str) -> None:
        self.collate_fn = collate_fn
        self.device = device

    def __call__(self, items: list[Any]) -> Any:
        batch = self.collate_fn(items)
        if hasattr(batch, "to"):
            return batch.to(self.device)
        return {k: v.to(self.device) if hasattr(v, "to") else v for k, v in batch.items()}


@dataclass
class LoadedAlertBERT:
    dataset_cls: Any
    model_cls: Any
    inference_wrapper_cls: Any
    timedelta_cls: Any
    eval_alert_grouping: Any
    label_vocabs: dict[str, Any]
    data_tools: dict[str, dict[str, Any]]
    model_id: str
    model: Any
    device: str


def load_alertbert_stack(model_id: str, config: str, device: str) -> LoadedAlertBERT:
    ab = import_alertbert()
    torch = import_torch()
    saved_models = ALERTBERT_DIR / "saved_models"
    label_vocabs = ab["load_ground_truth_label_vocabs"](str(saved_models), config)
    _reports, param_dicts = ab["load_reports"]([model_id], str(saved_models))
    data_tools = ab["load_data_tools"]([model_id], param_dicts, str(saved_models), label_vocabs)
    models = ab["load_models"](param_dicts, str(saved_models), data_tools, torch.device(device))
    models[model_id].eval()
    data_tools[model_id]["inf_coll_fn"] = DeviceCollate(data_tools[model_id]["inf_coll_fn"], device)
    return LoadedAlertBERT(
        dataset_cls=ab["AITAlertDataset"],
        model_cls=ab["AlertBERT"],
        inference_wrapper_cls=ab["MaskedLangModelInferenceWrapper"],
        timedelta_cls=ab["TimeDelta"],
        eval_alert_grouping=ab["eval_alert_grouping"],
        label_vocabs=label_vocabs,
        data_tools=data_tools,
        model_id=model_id,
        model=models[model_id],
        device=device,
    )


def load_dataset(
    stack: LoadedAlertBERT,
    split: str,
    config: str,
    max_scenarios: int | None = None,
    max_alerts_per_scenario: int | None = None,
) -> Any:
    data = stack.dataset_cls(split=split, configuration=config, path=str(ALERTBERT_DIR / "aitads_augmented"))
    if max_scenarios:
        data.scenarios = data.scenarios[:max_scenarios]
        data.n_scenarios = len(data.scenarios)
        data.split = data.split[:max_scenarios]
    if max_alerts_per_scenario:
        for scenario in data.scenarios:
            scenario.data = {k: v[:max_alerts_per_scenario] for k, v in scenario.data.items()}
    return data


def result_summary(result: dict[str, Any]) -> dict[str, float]:
    macro = result["summary"]["macro"]["macro"]
    keys = ["precision", "recall", "tnr", "f1", "mcc", "accuracy"]
    return {k: float(macro[k][0]) for k in keys if k in macro}


def eval_grouping(stack: LoadedAlertBERT, grouping_model: Any, data: Any) -> dict[str, Any]:
    stats_noise, _ = stack.eval_alert_grouping(
        model=grouping_model,
        target_vocab=stack.label_vocabs["hierarchical_event_label"],
        data=data,
        ignore_excluded_macro_label=False,
    )
    stats_clean, _ = stack.eval_alert_grouping(
        model=grouping_model,
        target_vocab=stack.label_vocabs["hierarchical_event_label"],
        data=data,
    )
    return {"noise": stats_noise, "clean": stats_clean}


def make_alertbert_grouping(
    stack: LoadedAlertBERT,
    delta: float,
    theta: float,
    dim_reduction: int = 2,
    component_library: str = "scipy",
) -> Any:
    class AlertBERTWithComponentLibrary(stack.model_cls):
        def __init__(self, *inner_args: Any, component_library: str = "scipy", **inner_kwargs: Any) -> None:
            super().__init__(*inner_args, **inner_kwargs)
            self.component_library = component_library

        def get_connected_components(self, coords_0: np.ndarray, coords_1: np.ndarray, n_nodes: int, library: str = "graph-tools") -> np.ndarray:
            return super().get_connected_components(coords_0, coords_1, n_nodes, library=self.component_library)

    wrapper = stack.inference_wrapper_cls(stack.model, ("embedding", "encoder"))
    return AlertBERTWithComponentLibrary(
        model=wrapper,
        collate_fn=stack.data_tools[stack.model_id]["inf_coll_fn"],
        dim_reduction=dim_reduction,
        delta=delta,
        theta=theta,
        component_library=component_library,
    )


def tune_alertbert(
    stack: LoadedAlertBERT,
    config: str,
    split: str,
    deltas: list[float],
    thetas: list[float],
    max_scenarios: int | None,
    output_dir: Path,
    component_library: str,
) -> tuple[float, float, pd.DataFrame]:
    rows = []
    data = load_dataset(stack, split=split, config=config, max_scenarios=max_scenarios)
    for delta in deltas:
        for theta in thetas:
            if theta < delta:
                continue
            started = time.time()
            grouping = make_alertbert_grouping(stack, delta, theta, component_library=component_library)
            result = eval_grouping(stack, grouping, data)["noise"]
            metrics = result_summary(result)
            rows.append({"delta": delta, "theta": theta, "seconds": time.time() - started, **metrics})
            print(f"tuned delta={delta} theta={theta} f1={metrics.get('f1', math.nan):.4f}")
    df = pd.DataFrame(rows).sort_values(["f1", "recall", "tnr"], ascending=False)
    output_dir.mkdir(parents=True, exist_ok=True)
    df.to_csv(output_dir / "tuning_results.csv", index=False)
    best = df.iloc[0]
    return float(best["delta"]), float(best["theta"]), df


def flatten_predictions(data: Any, pred_by_scenario: list[np.ndarray], embeddings_by_scenario: list[np.ndarray] | None = None) -> pd.DataFrame:
    rows: list[dict[str, Any]] = []
    global_cluster_offset = 0
    for scenario_idx, scenario in enumerate(data.scenarios):
        pred = pred_by_scenario[scenario_idx].astype(int)
        pred = pred + global_cluster_offset
        global_cluster_offset = int(pred.max()) + 1 if len(pred) else global_cluster_offset
        data_dict = scenario.data
        embeddings = embeddings_by_scenario[scenario_idx] if embeddings_by_scenario is not None else None
        for i in range(len(scenario)):
            event_label = str(data_dict.get("event_label", [""])[i])
            h_label = str(data_dict.get("hierarchical_event_label", [""])[i])
            rows.append(
                {
                    "scenario_idx": scenario_idx,
                    "alert_idx": i,
                    "cluster": int(pred[i]),
                    "time": float(data_dict.get("time", [np.nan])[i]),
                    "raw_time": float(data_dict.get("raw_time", [np.nan])[i]),
                    "name": str(data_dict.get("name", [""])[i]),
                    "short": str(data_dict.get("short", [""])[i]),
                    "host": str(data_dict.get("host", [""])[i]),
                    "ip": str(data_dict.get("ip", [""])[i]),
                    "event_label": event_label,
                    "hierarchical_event_label": h_label,
                    "is_attack": bool(event_label != "-" and h_label != "-"),
                    "emb_json": json.dumps(embeddings[i].tolist()) if embeddings is not None else "",
                }
            )
    return pd.DataFrame(rows)


def comb2(n: int) -> int:
    return n * (n - 1) // 2


def pairwise_metrics(true_labels: list[str], pred_labels: list[int]) -> dict[str, float]:
    true_counts = Counter(true_labels)
    pred_counts = Counter(pred_labels)
    joint_counts = Counter(zip(true_labels, pred_labels))
    tp = sum(comb2(v) for v in joint_counts.values())
    pred_pairs = sum(comb2(v) for v in pred_counts.values())
    true_pairs = sum(comb2(v) for v in true_counts.values())
    precision = tp / pred_pairs if pred_pairs else 0.0
    recall = tp / true_pairs if true_pairs else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    return {"pair_precision": precision, "pair_recall": recall, "pair_f1": f1}


def clustering_metrics(df: pd.DataFrame) -> dict[str, float]:
    adjusted_rand_score, normalized_mutual_info_score, hcv = import_sklearn_metrics()
    clean = df[df["hierarchical_event_label"] != "-"].copy()
    if clean.empty:
        return {}
    true = clean["hierarchical_event_label"].astype(str).tolist()
    pred = clean["cluster"].astype(int).tolist()
    homogeneity, completeness, v_measure = hcv(true, pred)
    metrics = {
        "ari": float(adjusted_rand_score(true, pred)),
        "nmi": float(normalized_mutual_info_score(true, pred)),
        "homogeneity": float(homogeneity),
        "completeness": float(completeness),
        "v_measure": float(v_measure),
    }
    metrics.update(pairwise_metrics(true, pred))
    return metrics


def entropy(values: pd.Series) -> float:
    counts = values.value_counts()
    total = counts.sum()
    if total == 0:
        return 0.0
    probs = counts / total
    return float(-(probs * np.log2(probs)).sum())


def compute_uncertainty(df: pd.DataFrame) -> pd.DataFrame:
    records = []
    for cluster, group in df.groupby("cluster", sort=False):
        emb = np.array([json.loads(x) for x in group["emb_json"]]) if group["emb_json"].iloc[0] else np.empty((len(group), 0))
        if emb.size and len(group) > 1:
            vec = emb[:, :-1] if emb.shape[1] > 1 else emb
            centroid = vec.mean(axis=0, keepdims=True)
            denom = np.linalg.norm(vec, axis=1) * max(float(np.linalg.norm(centroid)), 1e-12)
            sim = np.divide((vec * centroid).sum(axis=1), denom, out=np.zeros(len(vec)), where=denom != 0)
            centroid_uncertainty = float(1.0 - np.mean(sim))
        else:
            centroid_uncertainty = 1.0
        size = len(group)
        size_uncertainty = 1.0 / math.sqrt(size)
        host_entropy = entropy(group["host"]) / max(math.log2(max(group["host"].nunique(), 2)), 1.0)
        short_entropy = entropy(group["short"]) / max(math.log2(max(group["short"].nunique(), 2)), 1.0)
        time_span = float(group["raw_time"].max() - group["raw_time"].min())
        time_uncertainty = min(time_span / 3600.0, 1.0)
        score = 0.45 * centroid_uncertainty + 0.20 * size_uncertainty + 0.15 * host_entropy + 0.15 * short_entropy + 0.05 * time_uncertainty
        records.append(
            {
                "cluster": int(cluster),
                "cluster_size": int(size),
                "uncertainty": float(score),
                "centroid_uncertainty": float(centroid_uncertainty),
                "host_entropy": float(host_entropy),
                "short_entropy": float(short_entropy),
                "time_span": time_span,
                "true_attack_alerts": int(group["is_attack"].sum()),
                "true_attack_ratio": float(group["is_attack"].mean()),
            }
        )
    return pd.DataFrame(records).sort_values("uncertainty", ascending=False)


def representative_alerts(group: pd.DataFrame, limit: int) -> list[dict[str, Any]]:
    cols = ["raw_time", "name", "short", "host", "ip"]
    if len(group) <= limit:
        sample = group
    else:
        idx = np.linspace(0, len(group) - 1, num=limit, dtype=int)
        sample = group.iloc[idx]
    return sample[cols].to_dict(orient="records")


def extract_json(text: str) -> dict[str, Any]:
    match = re.search(r"\{.*\}", text, flags=re.S)
    if not match:
        raise ValueError("no JSON object found")
    return json.loads(match.group(0))


def normalize_decision(obj: dict[str, Any], raw_text: str = "") -> dict[str, Any]:
    allowed_decisions = {"attack", "benign", "uncertain"}
    allowed_types = {
        "service_scan",
        "dirb",
        "wpscan",
        "webshell_cmd",
        "crack_passwords",
        "privilege_escalation",
        "dnsteal",
        "unknown",
        "none",
    }
    decision = str(obj.get("decision", "uncertain")).lower()
    attack_type = str(obj.get("attack_type", "unknown")).lower()
    try:
        confidence = float(obj.get("confidence", 0.0))
    except (TypeError, ValueError):
        confidence = 0.0
    if decision not in allowed_decisions or confidence < 0.7:
        decision = "uncertain"
    if attack_type not in allowed_types:
        attack_type = "unknown"
    return {
        "decision": decision,
        "attack_type": attack_type,
        "confidence": max(0.0, min(confidence, 1.0)),
        "rationale": str(obj.get("rationale", ""))[:500],
        "raw_text": raw_text,
    }


def rules_triage(alerts: list[dict[str, Any]]) -> dict[str, Any]:
    text = " ".join(str(a.get("name", "")) + " " + str(a.get("short", "")) for a in alerts).lower()
    mapping = [
        ("wpscan", "wpscan"),
        ("dirb", "dirb"),
        ("webshell", "webshell_cmd"),
        ("sudo", "privilege_escalation"),
        ("password", "crack_passwords"),
        ("dns", "dnsteal"),
        ("scan", "service_scan"),
    ]
    for needle, attack_type in mapping:
        if needle in text:
            return {"decision": "attack", "attack_type": attack_type, "confidence": 0.75, "rationale": f"keyword match: {needle}"}
    return {"decision": "benign", "attack_type": "none", "confidence": 0.75, "rationale": "no attack keyword matched"}


class QwenClient:
    def __init__(self, model_path: Path, device: str, max_new_tokens: int) -> None:
        import torch
        from transformers import AutoModelForCausalLM, AutoTokenizer

        self.device = device
        self.max_new_tokens = max_new_tokens
        self.tokenizer = AutoTokenizer.from_pretrained(str(model_path), trust_remote_code=True)
        dtype = torch.bfloat16 if device.startswith("cuda") else torch.float32
        self.model = AutoModelForCausalLM.from_pretrained(str(model_path), torch_dtype=dtype, trust_remote_code=True)
        self.model.to(device)
        self.model.eval()

    def decide(self, alerts: list[dict[str, Any]]) -> tuple[dict[str, Any], int, int]:
        import torch

        system = (
            "You are a SOC triage assistant. Return only compact JSON. "
            "Allowed decisions: attack, benign, uncertain. "
            "Allowed attack_type values: service_scan, dirb, wpscan, webshell_cmd, "
            "crack_passwords, privilege_escalation, dnsteal, unknown, none."
        )
        user = {
            "task": "Classify whether this alert cluster needs analyst review.",
            "output_schema": {"decision": "attack|benign|uncertain", "attack_type": "string", "confidence": "0..1", "rationale": "short string"},
            "alerts": alerts,
        }
        messages = [{"role": "system", "content": system}, {"role": "user", "content": json.dumps(user, ensure_ascii=False)}]
        try:
            prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True, enable_thinking=False)
        except TypeError:
            prompt = self.tokenizer.apply_chat_template(messages, tokenize=False, add_generation_prompt=True)
        inputs = self.tokenizer([prompt], return_tensors="pt").to(self.device)
        input_tokens = int(inputs["input_ids"].shape[-1])
        with torch.no_grad():
            output_ids = self.model.generate(**inputs, max_new_tokens=self.max_new_tokens, do_sample=False)
        generated = output_ids[:, input_tokens:]
        output_tokens = int(generated.shape[-1])
        text = self.tokenizer.batch_decode(generated, skip_special_tokens=True)[0]
        try:
            decision = normalize_decision(extract_json(text), raw_text=text)
        except Exception as exc:  # noqa: BLE001
            decision = normalize_decision({"decision": "uncertain", "confidence": 0, "rationale": f"parse error: {exc}"}, raw_text=text)
        return decision, input_tokens, output_tokens


def triage_clusters(df: pd.DataFrame, uncertainty_df: pd.DataFrame, args: argparse.Namespace, device: str) -> tuple[pd.DataFrame, list[dict[str, Any]]]:
    n_select = max(1, int(math.ceil(len(uncertainty_df) * args.uncertain_top_pct)))
    n_select = min(n_select, args.max_llm_clusters)
    selected = set(uncertainty_df.head(n_select)["cluster"].astype(int).tolist())
    df = df.copy()
    df["sent_to_llm"] = df["cluster"].isin(selected)
    decisions: list[dict[str, Any]] = []
    qwen = None
    if args.llm_mode == "qwen":
        qwen = QwenClient(Path(args.model_path), device, args.max_new_tokens)
    for cluster in sorted(selected):
        group = df[df["cluster"] == cluster].sort_values("raw_time")
        alerts = representative_alerts(group, args.alerts_per_cluster)
        started = time.time()
        if args.llm_mode == "off":
            decision = {"decision": "uncertain", "attack_type": "unknown", "confidence": 0.0, "rationale": "llm disabled", "raw_text": ""}
            input_tokens = output_tokens = 0
        elif args.llm_mode == "rules":
            decision = normalize_decision(rules_triage(alerts), raw_text="")
            input_tokens = output_tokens = 0
        else:
            assert qwen is not None
            decision, input_tokens, output_tokens = qwen.decide(alerts)
        record = {
            "cluster": int(cluster),
            "cluster_size": int(len(group)),
            "true_attack_alerts": int(group["is_attack"].sum()),
            "true_attack_ratio": float(group["is_attack"].mean()),
            "input_tokens": input_tokens,
            "output_tokens": output_tokens,
            "seconds": time.time() - started,
            **decision,
        }
        decisions.append(record)
        print(f"triage cluster={cluster} size={len(group)} decision={decision['decision']} type={decision['attack_type']}")
    decision_map = {d["cluster"]: d for d in decisions}
    df["hybrid_decision"] = df["cluster"].map(lambda c: decision_map.get(int(c), {}).get("decision", "review"))
    return df, decisions


def triage_metrics(df: pd.DataFrame, decisions: list[dict[str, Any]], alerts_per_cluster: int) -> dict[str, Any]:
    retained = df["hybrid_decision"].isin(["review", "attack", "uncertain"])
    true = df["is_attack"].astype(bool)
    tp = int((retained & true).sum())
    fp = int((retained & ~true).sum())
    fn = int((~retained & true).sum())
    tn = int((~retained & ~true).sum())
    precision = tp / (tp + fp) if tp + fp else 0.0
    recall = tp / (tp + fn) if tp + fn else 0.0
    f1 = 2 * precision * recall / (precision + recall) if precision + recall else 0.0
    input_tokens = sum(int(d.get("input_tokens", 0)) for d in decisions)
    output_tokens = sum(int(d.get("output_tokens", 0)) for d in decisions)
    avg_tokens = (input_tokens + output_tokens) / max(len(decisions), 1)
    pure_llm_est = avg_tokens * int(df["cluster"].nunique()) if avg_tokens else 0
    return {
        "attack_precision": precision,
        "attack_recall": recall,
        "attack_f1": f1,
        "false_positive_alerts_retained": fp,
        "false_negative_attack_alerts": fn,
        "auto_benign_alerts": int((df["hybrid_decision"] == "benign").sum()),
        "total_alerts": int(len(df)),
        "total_clusters": int(df["cluster"].nunique()),
        "llm_clusters": int(len(decisions)),
        "llm_cluster_ratio": float(len(decisions) / max(df["cluster"].nunique(), 1)),
        "input_tokens": input_tokens,
        "output_tokens": output_tokens,
        "pure_llm_cluster_token_estimate": pure_llm_est,
        "alerts_per_cluster_prompt_cap": alerts_per_cluster,
    }


def run(args: argparse.Namespace) -> None:
    output_dir = Path(args.output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    preload_graph_tool()
    env = verify_env(output_dir)
    device = select_device(args.device)
    print(f"using device: {device}")
    stack = load_alertbert_stack(args.model_id, args.config, device)

    if args.quick:
        delta, theta = args.quick_delta, args.quick_theta
        tuning_df = pd.DataFrame([{"delta": delta, "theta": theta, "quick": True}])
        tuning_df.to_csv(output_dir / "tuning_results.csv", index=False)
    else:
        deltas = [float(x) for x in args.deltas.split(",")]
        thetas = [float(x) for x in args.thetas.split(",")]
        delta, theta, _ = tune_alertbert(stack, args.config, args.tune_split, deltas, thetas, args.max_scenarios, output_dir, args.component_library)
    print(f"selected delta={delta} theta={theta}")

    eval_data = load_dataset(
        stack,
        split=args.eval_split,
        config=args.config,
        max_scenarios=args.max_scenarios,
        max_alerts_per_scenario=args.max_alerts_per_scenario,
    )

    td = stack.timedelta_cls(delta=delta)
    td_result = eval_grouping(stack, td, eval_data)
    write_json(output_dir / "timedelta_test_metrics.json", {"noise": result_summary(td_result["noise"]), "clean": result_summary(td_result["clean"])})

    grouping = make_alertbert_grouping(stack, delta, theta, component_library=args.component_library)
    pred_by_scenario = []
    emb_by_scenario = []
    for scenario in eval_data.scenarios:
        pred_by_scenario.append(grouping(scenario))
        emb_by_scenario.append(grouping.get_embeddings(scenario))
    alert_df = flatten_predictions(eval_data, pred_by_scenario, emb_by_scenario)
    alert_df.drop(columns=["emb_json"]).to_csv(output_dir / "clusters.csv", index=False)

    alertbert_metrics = clustering_metrics(alert_df)
    alertbert_eval = eval_grouping(stack, grouping, eval_data)
    alertbert_metrics["alertbert_macro_noise"] = result_summary(alertbert_eval["noise"])
    alertbert_metrics["alertbert_macro_clean"] = result_summary(alertbert_eval["clean"])
    write_json(output_dir / "alertbert_test_metrics.json", alertbert_metrics)

    uncertainty_df = compute_uncertainty(alert_df)
    uncertainty_df.to_csv(output_dir / "cluster_uncertainty.csv", index=False)
    triaged_df, decisions = triage_clusters(alert_df, uncertainty_df, args, device)
    triaged_df.drop(columns=["emb_json"]).to_csv(output_dir / "hybrid_clusters.csv", index=False)
    with (output_dir / "qwen_decisions.jsonl").open("w", encoding="utf-8") as fh:
        for row in decisions:
            fh.write(json.dumps(row, ensure_ascii=False, default=json_default) + "\n")
    hybrid = triage_metrics(triaged_df, decisions, args.alerts_per_cluster)
    write_json(output_dir / "hybrid_metrics.json", hybrid)
    write_summary(output_dir, env, delta, theta, alertbert_metrics, hybrid, td_result)


def write_summary(output_dir: Path, env: dict[str, Any], delta: float, theta: float, alertbert_metrics: dict[str, Any], hybrid: dict[str, Any], td_result: dict[str, Any]) -> None:
    td_noise = result_summary(td_result["noise"])
    lines = [
        "# Hybrid AlertBERT + Qwen Summary",
        "",
        f"- Python: `{env.get('python')}`",
        f"- CUDA available: `{env.get('cuda_available')}`, devices: `{env.get('cuda_device_count')}`",
        f"- Selected AlertBERT params: `delta={delta}`, `theta={theta}`",
        "",
        "## Metrics",
        "",
        "| Method | Precision | Recall | TNR | F1 |",
        "|---|---:|---:|---:|---:|",
        f"| TimeDelta | {td_noise.get('precision', 0):.4f} | {td_noise.get('recall', 0):.4f} | {td_noise.get('tnr', 0):.4f} | {td_noise.get('f1', 0):.4f} |",
        f"| AlertBERT | {alertbert_metrics['alertbert_macro_noise'].get('precision', 0):.4f} | {alertbert_metrics['alertbert_macro_noise'].get('recall', 0):.4f} | {alertbert_metrics['alertbert_macro_noise'].get('tnr', 0):.4f} | {alertbert_metrics['alertbert_macro_noise'].get('f1', 0):.4f} |",
        f"| Hybrid triage | {hybrid.get('attack_precision', 0):.4f} | {hybrid.get('attack_recall', 0):.4f} | n/a | {hybrid.get('attack_f1', 0):.4f} |",
        "",
        "## Cost",
        "",
        f"- LLM clusters: `{hybrid.get('llm_clusters')}` / `{hybrid.get('total_clusters')}` ({hybrid.get('llm_cluster_ratio', 0):.2%})",
        f"- Prompt tokens: `{hybrid.get('input_tokens')}`, output tokens: `{hybrid.get('output_tokens')}`",
        f"- Pure cluster-level LLM token estimate: `{hybrid.get('pure_llm_cluster_token_estimate')}`",
    ]
    (output_dir / "summary.md").write_text("\n".join(lines) + "\n", encoding="utf-8")


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    verify = sub.add_parser("verify-env")
    verify.add_argument("--output-dir", default=None)

    run_p = sub.add_parser("run")
    run_p.add_argument("--config", default="simul-attacks")
    run_p.add_argument("--tune-split", default="val")
    run_p.add_argument("--eval-split", default="test")
    run_p.add_argument("--model-id", default=DEFAULT_MODEL_ID)
    run_p.add_argument("--device", default="auto")
    run_p.add_argument("--output-dir", default=str(ROOT / "outputs" / "hybrid_alertbert_qwen"))
    run_p.add_argument("--quick", action="store_true")
    run_p.add_argument("--quick-delta", type=float, default=24.0)
    run_p.add_argument("--quick-theta", type=float, default=128.0)
    run_p.add_argument("--component-library", choices=["scipy", "graph-tools"], default="scipy")
    run_p.add_argument("--deltas", default="8,12,16,24")
    run_p.add_argument("--thetas", default="32,64,128,256")
    run_p.add_argument("--max-scenarios", type=int, default=None)
    run_p.add_argument("--max-alerts-per-scenario", type=int, default=None)
    run_p.add_argument("--uncertain-top-pct", type=float, default=0.05)
    run_p.add_argument("--max-llm-clusters", type=int, default=20)
    run_p.add_argument("--llm-mode", choices=["off", "rules", "qwen"], default="qwen")
    run_p.add_argument("--model-path", default=str(DEFAULT_QWEN_PATH))
    run_p.add_argument("--max-new-tokens", type=int, default=256)
    run_p.add_argument("--alerts-per-cluster", type=int, default=20)
    return parser


def main() -> None:
    parser = build_parser()
    args = parser.parse_args()
    if args.command == "verify-env":
        verify_env(Path(args.output_dir) if args.output_dir else None)
    elif args.command == "run":
        run(args)
    else:
        parser.error(f"unknown command: {args.command}")


if __name__ == "__main__":
    main()
