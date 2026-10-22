"""Local personal-style QLoRA workflow. Preparation uses only the standard library."""
from __future__ import annotations

import argparse
from collections import defaultdict
import hashlib
import json
import os
from pathlib import Path
import random
import subprocess
import sys

ROOT = Path(__file__).resolve().parents[1]
BASE = ROOT / "finetune"
MODEL = "mlx-community/Qwen3-4B-Instruct-2507-4bit"
SYSTEM = "根据对话自然回复，保持个人表达习惯。不要编造事实。"
# This model's cached chat template inserts this before the final training reply,
# but add_generation_prompt emits only the assistant role header. Supply the
# same empty reasoning preamble for both base and adapter comparisons.
REPLY_PREFILL = "<think>\n\n</think>\n\n"


def prepare(source: Path, me: str, output: Path, split_plan: Path | None = None):
    chats = json.loads(source.read_text(encoding="utf-8"))
    if not isinstance(chats, list):
        raise ValueError("输入应为 conversation 对象组成的 JSON 数组")
    groups = defaultdict(list)
    seen = set()
    prompt_groups = {}
    for chat in chats:
        group = chat.get("conversation_id")
        if not isinstance(group, str) or not group.strip():
            raise ValueError("每段对话必须有非空 conversation_id")
        history = []
        for message in chat["messages"]:
            speaker, text = message.get("speaker"), message.get("text")
            if not isinstance(speaker, str) or not speaker.strip():
                raise ValueError("每条消息必须有 speaker")
            if not isinstance(text, str) or not text.strip():
                raise ValueError("每条消息必须有非空 text；先去掉图片、语音等占位消息")
            role = "assistant" if speaker == me else "user"
            text = text.strip()
            if history and history[-1]["role"] == role:
                history[-1]["content"] += "\n" + text
            else:
                history.append({"role": role, "content": text})
        # One sample for each of my turns, with bounded conversational context.
        for i, message in enumerate(history):
            if message["role"] != "assistant" or i == 0:
                continue
            start = max(0, i - 5)
            if history[start]["role"] == "assistant":
                start += 1
            context = history[start:i + 1]
            if not context or context[0]["role"] != "user":
                continue
            prompt_key = json.dumps(context[:-1], ensure_ascii=False, sort_keys=True)
            previous_group = prompt_groups.get(prompt_key)
            if previous_group is not None and previous_group != group:
                raise ValueError("跨 conversation_id 出现相同上下文；请合并重复对话后重试，避免测试泄漏")
            prompt_groups[prompt_key] = group
            sample = {"messages": [{"role": "system", "content": SYSTEM}] + context}
            fingerprint = hashlib.sha256(json.dumps(sample, sort_keys=True).encode()).hexdigest()
            if fingerprint not in seen:
                groups[group].append(sample)
                seen.add(fingerprint)
    keys = sorted(groups)
    if len(keys) < 3 or len(seen) < 10:
        raise ValueError("至少需要 3 段独立对话和 10 条本人回复才能划分数据；正式实验建议先整理 100–300 条")
    if split_plan is not None:
        splits = json.loads(split_plan.read_text(encoding="utf-8"))
        if not isinstance(splits, dict) or set(splits) != {"train", "valid", "test"}:
            raise ValueError("划分计划必须包含 train、valid、test")
        for ids in splits.values():
            if not isinstance(ids, list) or not ids or not all(isinstance(key, str) for key in ids):
                raise ValueError("每个集合必须包含非空对话 ID 列表")
        assigned = [key for ids in splits.values() for key in ids]
        if len(assigned) != len(set(assigned)):
            raise ValueError("划分计划中对话 ID 重复，会造成数据泄漏")
        if set(assigned) != set(keys):
            raise ValueError("划分计划必须恰好覆盖所有有样本的对话 ID")
    else:
        random.Random(42).shuffle(keys)
        count = max(1, len(keys) // 10)
        splits = {"test": keys[:count], "valid": keys[count:2 * count], "train": keys[2 * count:]}
    if output.exists() and any(output.iterdir()):
        raise ValueError("输出目录已有内容；请指定新的 --output 目录，避免覆盖旧数据")
    output.mkdir(parents=True, exist_ok=True)
    manifest = {"source_sha256": hashlib.sha256(source.read_bytes()).hexdigest(), "seed": 42 if split_plan is None else None, "split_method": "explicit" if split_plan else "random", "splits": {}}
    if split_plan:
        manifest["split_plan_sha256"] = hashlib.sha256(split_plan.read_bytes()).hexdigest()
    for split, ids in splits.items():
        samples = [sample for key in ids for sample in groups[key]]
        (output / f"{split}.jsonl").write_text("".join(json.dumps(s, ensure_ascii=False) + "\n" for s in samples), encoding="utf-8")
        manifest["splits"][split] = {"conversations": len(ids), "examples": len(samples), "conversation_ids": ids}
    (output / "manifest.json").write_text(json.dumps(manifest, indent=2), encoding="utf-8")
    print(json.dumps(manifest["splits"], ensure_ascii=False, indent=2))


def run_mlx(module, args):
    os.environ.setdefault("HF_HOME", str(BASE / "hf-cache"))
    os.environ.setdefault("HF_HUB_DISABLE_TELEMETRY", "1")
    subprocess.run([sys.executable, "-m", "mlx_lm", module.removeprefix("mlx_lm."), *args], cwd=ROOT, check=True)


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    commands = parser.add_subparsers(dest="command", required=True)
    prep = commands.add_parser("prepare")
    prep.add_argument("source", type=Path)
    prep.add_argument("--me", required=True, help="与你本人消息的 speaker 完全一致")
    prep.add_argument("--output", type=Path, default=BASE / "private/prepared")
    prep.add_argument("--split-plan", type=Path)
    train = commands.add_parser("train")
    train.add_argument("--iters", type=int, default=100)
    train.add_argument("--resume", action="store_true")
    evaluate = commands.add_parser("evaluate")
    generate = commands.add_parser("generate")
    generate.add_argument("prompt")
    generate.add_argument("--base", action="store_true", help="不加载 adapter，比较原模型")
    serve = commands.add_parser("serve")
    for command in (train, evaluate, generate, serve):
        command.add_argument("--adapter-path", type=Path, default=BASE / "adapters/zoe")
    for command in (train, evaluate):
        command.add_argument("--data", type=Path, default=BASE / "private/prepared")
    args = parser.parse_args()
    adapter = getattr(args, "adapter_path", BASE / "adapters/zoe").resolve()
    data = getattr(args, "data", BASE / "private/prepared").resolve()
    if args.command == "prepare":
        prepare(args.source, args.me, args.output, args.split_plan)
        return
    if args.command == "train":
        if args.iters < 1:
            raise ValueError("iters 必须为正数")
        for split in ("train", "valid", "test"):
            if not (data / f"{split}.jsonl").is_file():
                raise ValueError("先用 prepare 准备真实数据")
        weights = adapter / "adapters.safetensors"
        extra = []
        if args.resume:
            if not weights.exists():
                raise ValueError("没有可恢复的 adapter")
            extra = ["--resume-adapter-file", str(weights)]
        elif adapter.exists() and any(adapter.iterdir()):
            raise ValueError("已有训练产物；用 --resume 继续，或先移动旧 adapter")
        run_mlx("mlx_lm.lora", ["--config", str(BASE / "config.yaml"), "--data", str(data), "--adapter-path", str(adapter), "--iters", str(args.iters), "--val-batches", "-1", *extra])
        return
    base_only = args.command == "generate" and args.base
    if not base_only and not (adapter / "adapters.safetensors").is_file():
        raise ValueError("还没有训练好的 adapter；请先准备数据并 train")
    model_args = ["--model", MODEL] + ([] if base_only else ["--adapter-path", str(adapter)])
    if args.command == "generate":
        run_mlx("mlx_lm.generate", [*model_args, "--system-prompt", SYSTEM, "--prompt", args.prompt, "--prefill-response", REPLY_PREFILL, "--max-tokens", "256", "--temp", "0", "--seed", "42"])
    elif args.command == "evaluate":
        run_mlx("mlx_lm.lora", [*model_args, "--data", str(data), "--test", "--test-batches", "-1", "--batch-size", "1", "--max-seq-length", "1024", "--mask-prompt"])
    elif args.command == "serve":
        run_mlx("mlx_lm.server", [*model_args, "--host", "127.0.0.1", "--port", "8081"])


if __name__ == "__main__":
    try:
        main()
    except (ValueError, KeyError, TypeError, OSError, subprocess.CalledProcessError) as exc:
        sys.exit(f"失败：{exc}")
