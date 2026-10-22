# 本地训练个人语气（M4 Pro / 24GB）

采用 MLX + Qwen3-4B-Instruct-2507 的 4-bit QLoRA。只训练少量 adapter 参数。
这是一套待真实数据验证的起始配置，不代表模型已经学会你的语气。

## 1. 环境

在项目根目录运行：

```sh
/opt/homebrew/bin/python3.12 -m venv .venv-finetune
.venv-finetune/bin/python -m pip install -r finetune/requirements.txt
```

独立于原 agent 环境。首次运行模型会下载约 2.3GB 的权重到
`finetune/hf-cache/`，并需要额外磁盘空间存放依赖和 adapter。

## 2. 整理本人回复

复制 `chats.example.json` 的结构，把真实聊天导出转换成 JSON 数组，保存到
`finetune/private/chats.json`（自行创建 private 文件夹）。例子是格式占位，不是训练数据。

- 每个对象有 `conversation_id` 和 `messages`。
- 每条消息有 `speaker`、`text`；本人 speaker 建议统一为 `me`。
- 每段对话最好是双人聊天；群聊请先整理，避免丢失发言人含义。
- 不同日期/会话使用不同 ID。同一段对话不要拆到多个 ID。
- 只把你亲自写过或审核确认的文字标成 `me`；不要自动导入 agent 历史里的 assistant 回答。
- 去掉不希望模型学到的个人信息、引用和图片/语音占位符。
- 起步建议 100–300 条本人回复，至少覆盖十几段对话。

```sh
.venv-finetune/bin/python finetune/local.py prepare finetune/private/chats.json --me me
```

脚本将连续同角色消息合并，提取以本人回复结尾的样本，去重后按整段对话划分
约 80%/10%/10% 的 train/valid/test；最低 3 段对话、10 条回复只是格式验证门槛。
相同上下文跨会话会被拒绝，近似重复仍需人工清理。目标回复之外的上下文不计训练损失。
所有真实数据、模型缓存、训练权重均被 Git 忽略；不自动上传数据，不开启远程训练日志。

## 3. 训练

先短跑检查内存和 loss：

```sh
.venv-finetune/bin/python finetune/local.py train --iters 5
```

保留短跑产物继续训练：

```sh
.venv-finetune/bin/python finetune/local.py train --resume --iters 100
```

这里 iters 是本次运行的小批次迭代次数，不是 epoch 或累计目标。
当前每 4 个小批次更新一次参数，因此 100 次迭代约有 25 次参数更新，只是起步预算。
观察验证 loss，持续上升时不要盲目继续。配置为 batch=1、1024 tokens、8 层 LoRA、
rank=8、梯度检查点，显存/统一内存峰值需要实测。超长样本可能被截断，整理时优先保留短对话。
内存紧张时先关闭大应用，再把 config.yaml 的 num_layers 调至 4、max_seq_length 调至 512。

## 4. 比较与评估

```sh
.venv-finetune/bin/python finetune/local.py generate '今晚要一起吃饭吗？' --base
.venv-finetune/bin/python finetune/local.py generate '今晚要一起吃饭吗？'
.venv-finetune/bin/python finetune/local.py evaluate
```

用没训练过的问题盲评：像不像本人、是否答非所问、是否编造事实。
测试 loss 只衡量预测本人回复的能力，不能单独证明语气相似或 agent 能力。

## 5. 本地服务

```sh
.venv-finetune/bin/python finetune/local.py serve
```

提供 `http://127.0.0.1:8081/v1` 的 OpenAI-compatible 接口。
训练并验证后，可作为独立语气层接入；本次没有切换现有 agent 的主模型。
语气改写数据应另外准备“原回答 → 本人改写”，不能假设聊天模型能可靠保持全部事实。

参考：[MLX LoRA 文档](https://github.com/ml-explore/mlx-lm/blob/main/mlx_lm/LORA.md)、
[底座模型](https://huggingface.co/mlx-community/Qwen3-4B-Instruct-2507-4bit)。

## 固定分组与独立实验

`prepare --split-plan <JSON文件>` 接受 `train`、`valid`、`test` 三个键，
每个值是 conversation_id 的非空数组，必须无重叠且覆盖全部有样本的对话。
manifest 会记录源数据哈希、划分计划哈希和各集合的对话 ID。
新增数据不应自动改变已固定的验证/测试分组。扩充后修改计划时要检查分组完整性。

本次教学实验 prepared-v7 已生成：110 条训练、4 条验证、13 条测试。
加入当前对话中 11 条用户亲写回复，助手文字仅作上下文，未作为语气目标。
验证集很小，loss 的波动不能独立证明语气质量；保留未训练的生活类问题作人工比较。

运行新实验（不会加载之前 zoe 目录的 adapter）：

```sh
.venv-finetune/bin/python finetune/local.py train \
  --data finetune/private/prepared-v7 \
  --adapter-path finetune/adapters/zoe-v7 \
  --iters 100
```

训练后指定同一个 adapter 来试回复：

```sh
.venv-finetune/bin/python finetune/local.py generate '今天忙了一天，好累啊' \
  --adapter-path finetune/adapters/zoe-v7
```

如需计算这轮测试集 loss，明确指定对应数据和 adapter：

```sh
.venv-finetune/bin/python finetune/local.py evaluate \
  --data finetune/private/prepared-v7 \
  --adapter-path finetune/adapters/zoe-v7
```

`--resume` 只载入 adapter 权重，不恢复优化器状态和数据迭代位置；
这是从已有权重继续训练，不是完整恢复中断时的训练状态。

### v7 空输出排查

100 步 adapter 在普通 assistant header 后，对测试问题的贪心解码首 token
是 `<|im_end|>`，因此没有文字输出；25/50/75 步 checkpoint 对同一问题仍有文字。
当前底座缓存的聊天模板会在最终训练回复前插入空 `<think>…</think>`，
但单纯 add_generation_prompt 不包含这段前缀。local.py 的 generate 现已用
`--prefill-response` 为底座和 adapter 都补齐同样的空前缀。
三个手动探针恢复了文字输出，但出现复述输入，语气效果仍需评估。
模板不一致是已确认的问题，不能仅凭此认定 adapter 的全部质量问题都已解决。
该修正针对上述固定模型；换底座时须重新检查模板。serve 接口尚未套用此修正，
验证前不要把该 adapter 直接接到原 agent。loss 下降不能替代生成质量检查。
