# 可配置中转站 `gpt-image-2` 工具（下方验收记录仅适用原站）

从 skill 目录调用 `python3 scripts/image_gen_gateway.py`。首次在使用者本机运行 `configure --base-url https://YOUR-GATEWAY/v1`，终端私密输入自己的网关 API Key（或 `--key-env VARIABLE_NAME` 从环境导入）；以后不必重复填写。网关 URL/Key 存在 skill 外部的用户私有配置中，详见主 SKILL.md。图片模型固定 `gpt-image-2`，不改 Hermes 主模型，不重启网关。默认不使用聊天模型的 `OPENAI_API_KEY`，也不会改动官方原版 `scripts/image_gen.py`。

依赖：Python 3.11+，安装 `requirements.txt`；按主 SKILL.md 创建 `.venv` 后使用 `.venv/bin/python scripts/image_gen_gateway.py ...`，或先激活 venv 再使用下方 `python3` 示例。回归测试：从 skill 目录运行 `.venv/bin/python -m unittest discover -s tests -q`。可移植运行只需 `scripts/image_gen_gateway.py`、`scripts/gateway_image2.py`、`scripts/gateway_prompt.py`。下方示例须在 skill 目录执行，路径和输出目录按本机实际情况替换。**“本中转站/网关实测”均指原站的历史验收，别的站必须独立冒烟测试。**

## 可复制命令

```bash
python3 scripts/image_gen_gateway.py generate --prompt 'A natural-light portrait' --size 1024x1024 --quality medium --out ./output/imagegen/portrait.png
python3 scripts/image_gen_gateway.py edit --image /path/to/source.png --prompt 'Change the background only' --out ./output/imagegen/edit.png
python3 scripts/image_gen_gateway.py edit --image /path/to/target.png --image /path/to/reference.png --prompt 'Edit image 1 using image 2 as a color reference' --out ./output/imagegen/multi.png
python3 scripts/image_gen_gateway.py edit --image /path/to/source.png --mask /path/to/mask.png --prompt 'Change the masked area only' --out ./output/imagegen/masked.png
python3 scripts/image_gen_gateway.py generate --prompt 'One green leaf, transparent background' --background transparent --output-format webp --out ./output/imagegen/leaf.webp
python3 scripts/image_gen_gateway.py generate --prompt 'A red kite' --size 2048x1152 --stream --partial-images 1 --out ./output/imagegen/kite.png
python3 scripts/image_gen_gateway.py generate-batch --input /path/to/jobs.jsonl --out-dir ./output/imagegen/batch --concurrency 2
python3 scripts/image_gen_gateway.py tool --prompt 'Draw a yellow pear' --out ./output/imagegen/pear.png
python3 scripts/image_gen_gateway.py tool --image ./output/imagegen/pear.png --prompt 'Recolor the pear blue' --action edit --out ./output/imagegen/blue-pear.png
python3 scripts/image_gen_gateway.py tool --prompt 'Draw a single purple plum on white' --stream --partial-images 2 --quality low --out ./output/imagegen/plum.png
```

`tool` 是独立的 Responses API 图像工具路径：原站使用 `gpt-6-astra` 作为宿主模型，图像工具固定 `gpt-image-2`。其他中转站在 `configure --host-model MODEL` 时指定其可用的 Responses 宿主模型，或单次用 `--mainline-model MODEL` 覆盖；未指定则默认尝试 `gpt-6-astra`，**不保证别的站支持此路径**。强制 `--action edit`＋本地 `--image` 已在原站验收成功。**可靠的续改方式是把上轮输出文件再用 `--image` 传入**；本中转站仅给 `--previous-response-id`、不给图片会报 502，且 GET `/v1/responses/{id}` 返回 404，脚本现在本地拒绝这种用法。带 ID 又带本地图可生图，但未证明 ID 历史真的被利用。`--image-url` 已实测 Wikimedia 的 HTTPS 图片可供上游下载并编辑（右下角增加蓝圈）；另一个 OpenAI 文档站的图片在上游报“Failed to download file”（400），具体 URL 要以实际可下载为准。`--file-id` 的前置上传到网关 `/v1/files` 报“Model name not specified”（400），因此 File ID 入口已实现协议构造、**当前网关未打通**。日常编辑首选 Images `edit`；对话式图片编辑用 `tool --image`。

## 参数、输入及验证

- Images `generate`：文字；`edit`：第一张本地目标图，可多次 `--image` 附加参考图（支持 PNG/JPEG/WebP）；`--mask` 为**同第一张实际尺寸**的带 alpha PNG（透明区域是编辑区域）。生成后需目视确认不变量。
- `--size`：auto 或满足 GPT Image 2 约束的 WIDTHxHEIGHT（边为 16 倍数、长边不超过 3840、比例不超过 3:1、总像素 655360~8294400）；模型**实际返回尺寸可能不等于请求尺寸**。制作编辑遮罩时先读实际源图尺寸。
- `--quality auto|low|medium|high`、`--background auto|opaque|transparent`、`--output-format png|jpeg|webp`、JPEG/WebP `--output-compression 0..100`、`--moderation auto|low`；透明背景不能用 JPEG。`--output-format jpeg --out x.jpg` 或 `.jpeg` 均可。图片会做格式、可解码与输出数量校验，不覆盖既有文件（除非 `--force`）。
- `--n 1..10` 在本中转站**明确拆成 n 次单图请求**（实测网关直接 `n=2` 返回数量不足），任何子请求失败会在落盘整组前报错；因此费用与 n 张调用对应。批量 JSONL 可为单行字符串或字段对象；默认串行，`--concurrency` 1..4。失败不静默重试、无跨渠道 fallback；批次中其它任务可能已成功，查看输出目录。用全新输出目录重跑，避免覆盖。
- Images `--stream` 的最终图已验证，`--partial-images` 0..3 可请求预览，但实测该路由请求 1 和 2 张时均只回最终图；**图片生成快时官方也允许不返回预览**。Responses `tool --stream --partial-images 2` 已实测收到并即时落盘 2 张局部预览和 1 张最终图（也可能少于请求数）。流式暂不与 Images `--n>1` 组合。预览文件在对应最终图附近、文件名含 `-partial-`；无 `--force` 时预先防覆盖。
- 旧版提示词 `--augment/--no-augment`、`--use-case`、`--style` 等结构化字段及 `--downscale-max-dim`、`--downscale-suffix` 已保留；默认按旧版增强。`--dry-run` 不调用 API；运行前可用它验证参数。
- 实测 WebP 请求中转站仍返回 PNG；工具会打印“gateway returned PNG, converting locally to WEBP”，随后本地转换、验证格式，Alpha 保留。**这不是网关原生 WebP 成功**。透明 PNG 实测有 Alpha (0..254)。不得静默把 PNG 改名为 WebP。
- `--model` 和 `--input-fidelity` 不接受：此入口刻意固定图像模型，而 Image 2 不暴露后者。URL/File ID 的 Images JSON 编辑路径目前没有入口；需要时先验收中转站 API，再加，不能假装支持。

## 真实验收记录（2026-10-22）

- 公网中转站通过并目视核对：文生水彩红苹果；苹果＋文字加叶；双图参考变蓝苹果；Alpha 遮罩局部加叶；透明 PNG 绿叶；WebP 本地转换后的透明绿叶；流式最终蓝茶杯；2 条 JSONL 产出 3 张（两橙一紫李）；Responses tool 生成黄梨与 `--image`+auto 改蓝梨；Responses 强制 `--action edit --image ...` 改蓝苹果及显式携带本地图续改为绿苹果；Responses `--stream --partial-images 2` 得到 2 张局部预览＋1 张最终紫李；Responses `--image-url` 引用 Wikimedia 样本成功在右下角增加蓝圈；旧提示词增强＋缩略图生成红风筝。
- 未打通/有限制：Images `n=2` 单请求返回数量不足（工具已改为独立请求）；Responses `gpt-5.5` 宿主 `model_not_found`；仅靠历史 ID 续改缺图片上下文而 502，按 ID 检索图片 404（必须本地 `--image`）；HTTPS URL 图片仅在上游可下载时可用，Wikimedia 成功、OpenAI 文档站示例失败；网关上传视觉 File 的 `/v1/files` 报缺模型名 400；Images 流式未收到预览。旧版强制 edit 的 503 不是稳定失败：同脚本同入口本次复测成功。以上**不是** Image 2 模型自身不支持的证明，只是当前中转站路径的实测结果。
- 原站样图保存在原站本地，**不随共享 skill 分发**。调用失败不得换第三方生图服务；先报状态码和机器错误码，不打印 API 原文、密钥或图片 Base64。

官方参考：[Image generation guide](https://developers.openai.com/api/docs/guides/image-generation)、[GPT Image 2](https://developers.openai.com/api/docs/models/gpt-image-2)、[Responses image tool](https://developers.openai.com/api/docs/guides/tools-image-generation)。图片发飞书见 `references/feishu-image-delivery.md`。
