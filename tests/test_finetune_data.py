import contextlib
import io
import json
from pathlib import Path
import tempfile
import unittest
from unittest.mock import patch

from finetune.local import REPLY_PREFILL, main, prepare


class PersonalTrainingDataTests(unittest.TestCase):
    def chats(self):
        return [
            {"conversation_id": str(i), "messages": [
                {"speaker": "friend", "text": f"question {i}"},
                {"speaker": "me", "text": f"my answer {i}"},
                {"speaker": "friend", "text": f"follow up {i}"},
                {"speaker": "me", "text": f"my second answer {i}"},
            ]} for i in range(10)
        ]

    def prepare_in(self, root, chats):
        source = root / "source.json"
        source.write_text(json.dumps(chats), encoding="utf-8")
        with contextlib.redirect_stdout(io.StringIO()):
            prepare(source, "me", root / "prepared")

    def test_only_my_replies_are_targets_and_conversations_do_not_leak(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            self.prepare_in(root, self.chats())
            groups = []
            for split in ("train", "valid", "test"):
                rows = [json.loads(line) for line in (root / "prepared" / f"{split}.jsonl").read_text().splitlines()]
                ids = set()
                for row in rows:
                    messages = row["messages"]
                    self.assertEqual(messages[-1]["role"], "assistant")
                    self.assertTrue(messages[-1]["content"].startswith("my "))
                    ids.add(messages[-1]["content"].split()[-1])
                groups.append(ids)
            self.assertFalse(groups[0] & groups[1] or groups[1] & groups[2] or groups[0] & groups[2])
            self.assertEqual(len(set.union(*groups)), 10)
            with self.assertRaisesRegex(ValueError, "已有内容"):
                self.prepare_in(root, self.chats())

    def test_duplicate_context_across_conversations_is_rejected(self):
        chats = self.chats()
        chats[1]["messages"][0]["text"] = chats[0]["messages"][0]["text"]
        with tempfile.TemporaryDirectory() as directory:
            with self.assertRaisesRegex(ValueError, "相同上下文"):
                self.prepare_in(Path(directory), chats)

    def test_missing_personal_data_is_rejected(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            with self.assertRaisesRegex(ValueError, "至少需要"):
                self.prepare_in(root, self.chats()[:1])
            self.assertFalse((root / "prepared").exists())

    def test_explicit_plan_preserves_groups_and_rejects_leakage(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            source = root / "source.json"
            source.write_text(json.dumps(self.chats()), encoding="utf-8")
            plan_file = root / "plan.json"
            plan = {"train": [str(i) for i in range(8)], "valid": ["8"], "test": ["9"]}
            plan_file.write_text(json.dumps(plan), encoding="utf-8")
            with contextlib.redirect_stdout(io.StringIO()):
                prepare(source, "me", root / "prepared", plan_file)
            manifest = json.loads((root / "prepared/manifest.json").read_text())
            self.assertEqual(manifest["split_method"], "explicit")
            self.assertEqual(manifest["splits"]["train"]["examples"], 16)
            self.assertEqual(manifest["splits"]["test"]["conversation_ids"], ["9"])
            plan["test"] = ["8"]
            plan_file.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "重复"):
                prepare(source, "me", root / "bad", plan_file)
            self.assertFalse((root / "bad").exists())
            plan["test"] = ["unknown"]
            plan_file.write_text(json.dumps(plan), encoding="utf-8")
            with self.assertRaisesRegex(ValueError, "恰好覆盖"):
                prepare(source, "me", root / "bad", plan_file)

    def test_training_uses_requested_data_and_new_adapter_directory(self):
        with tempfile.TemporaryDirectory() as directory:
            root = Path(directory)
            data = root / "data"
            data.mkdir()
            for split in ("train", "valid", "test"):
                (data / f"{split}.jsonl").write_text('{}\n')
            adapter = root / "new-adapter"
            argv = ["local.py", "train", "--data", str(data), "--adapter-path", str(adapter), "--iters", "100"]
            with patch("sys.argv", argv), patch("finetune.local.run_mlx") as run:
                main()
            module, args = run.call_args.args
            self.assertEqual(module, "mlx_lm.lora")
            self.assertEqual(args[args.index("--data") + 1], str(data.resolve()))
            self.assertEqual(args[args.index("--adapter-path") + 1], str(adapter.resolve()))
            self.assertNotIn("--resume-adapter-file", args)

    def test_base_and_adapter_generation_share_training_reply_prefix(self):
        with tempfile.TemporaryDirectory() as directory:
            adapter = Path(directory)
            (adapter / "adapters.safetensors").touch()
            for base in (False, True):
                argv = ["local.py", "generate", "今天好累", "--adapter-path", str(adapter)]
                if base:
                    argv.append("--base")
                with patch("sys.argv", argv), patch("finetune.local.run_mlx") as run:
                    main()
                module, args = run.call_args.args
                self.assertEqual(module, "mlx_lm.generate")
                self.assertEqual(args[args.index("--prefill-response") + 1], REPLY_PREFILL)
                self.assertEqual("--adapter-path" in args, not base)


if __name__ == "__main__":
    unittest.main()
