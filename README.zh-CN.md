# GPT Image Gateway Skill（Image 2 / 2.5）

[English](README.md) | [简体中文](README.zh-CN.md)

可移植的 [Agent Skill](https://agentskills.io/specification)＋本地 Python CLI，用**使用者自己配置的 OpenAI 兼容图片中转站**直调 `gpt-image-2`、`gpt-image-2.5-flare`、`gpt-image-2.5-sunburst`。每位使用者首次配置自己的 URL/API Key；不带 MCP、托管服务或内置 Key，也不暗中切换提供方。

## 安装与首次配置

需要 Python 3.11+、可访问的兼容中转站及其私有 API Key。

```bash
git clone https://github.com/lih54767-coder/gpt-image-2-gateway-skill.git
cd gpt-image-2-gateway-skill
python3 -m venv .venv
.venv/bin/python -m pip install -r requirements.txt
.venv/bin/python scripts/image_gen_gateway.py configure --base-url https://YOUR-GATEWAY.example/v1
.venv/bin/python scripts/image_gen_gateway.py status
.venv/bin/python scripts/image_gen_gateway.py generate --prompt 'A blue triangle' --out ./output/triangle.png
```

`configure` 在**本地终端隐藏输入中转站 API Key**，不要把 Key 放进聊天、命令参数或仓库。自动化场景可通过密钥管理器注入临时环境变量，再使用 `--key-env 变量名`。配置时用该 Key 查询这个中转站的 `/v1/models`，将其广告的图片型号缓存于私有配置；认证或网络失败会停止配置，**不会误判为“只有 Image 2”**。型号列表也不能单独证明生图、改图或 Responses 路径全可用，新站点须分别实测。

`config.json`（URL、缓存型号、可选 Responses 宿主模型）和 `key` 都放在**仓库外**：Unix 为 `${XDG_CONFIG_HOME:-~/.config}/gpt-image-2-skill/`（文件权限 `0600`），Windows 为 `%LOCALAPPDATA%\gpt-image-2-skill\`（当前用户 ACL）。多个 Agent 共用操作系统账号时，用 `IMAGE2_CONFIG_DIR` 隔离。单次 `IMAGE2_API_KEY` 可覆盖已存的 Key；权限变化后须重跑 `configure` 刷新缓存。它不是 Agent 文本模型 Key，更不是公开浏览器 Key。

Windows 11 PowerShell：用 `py -3 -m venv .venv` 创建环境，把上述 `.venv/bin/python` 换成 `.\.venv\Scripts\python.exe`，脚本路径改为 `scripts\image_gen_gateway.py`。

## 模型选择和用法

`generate`、`edit`、`generate-batch` 默认 `--model auto`：

- 单张正式成图／精修优先 **Sunburst**；快稿加 `--quality low` 或明确指定 **Flare**；未指定型号的批量任务默认偏 **Flare**。
- 只有 Image 2 时用 `gpt-image-2`；只开通一种 2.5 时选择那一种。用户明确 `--model` 优先，失败也**不暗中换型号**。

```bash
.venv/bin/python scripts/image_gen_gateway.py generate --prompt 'A tiny leaf' --quality low --out ./output/draft.png
.venv/bin/python scripts/image_gen_gateway.py generate --model gpt-image-2.5-sunburst --quality xhigh --prompt 'Detailed watercolor leaf' --out ./output/final.png
.venv/bin/python scripts/image_gen_gateway.py edit --image ./source.png --image ./reference.png --mask ./mask.png --prompt 'Change the leaf color' --out ./output/edit.png
.venv/bin/python scripts/image_gen_gateway.py generate-batch --input ./jobs.jsonl --out-dir ./output/batch
.venv/bin/python scripts/image_gen_gateway.py tool --mainline-model YOUR_SUPPORTED_TEXT_MODEL --image ./source.png --action edit --prompt 'Recolor it' --out ./output/tool-edit.png
```

`--mask` 应为和**第一张输入图的实际尺寸**一致的带 Alpha PNG；透明区域是编辑引导，不能保证像素级严格不变。多次传 `--image` 可带参考图；`--n` 使用多个单图请求，防止网关返回张数不足。2.5 新增 `--quality xhigh|max`。还支持 PNG/JPEG/WebP 输出、透明、定制尺寸、压缩、流式输出（局部预览不保证）、本地缩图。见 [SKILL.md](SKILL.md) 和 [完整命令参考](references/gateway-image2.md)。

`tool` 是**独立的 Responses API 图片工具路径**：顶层文本宿主模型不同于图片工具型号，且要求中转站额外支持。普通生图/改图优先走 Images API。连续编辑须把上一张输出重新用 `--image` 传入；单靠历史 Response ID / File ID 不保证可用。

## 验收范围

离线测试同时在 Ubuntu/Windows CI 执行；本地用隔离配置测试，避免借用已有私密配置：

```bash
XDG_CONFIG_HOME=/tmp/image-skill-clean-test .venv/bin/python -m unittest discover -s tests -q
```

Windows PowerShell 可在新的私有配置目录下运行 `.\.venv\Scripts\python.exe -m unittest discover -s tests -q`。**单测不能证明其他中转站可用**。原站分别实测两款 2.5 的直调生图/改图、遮罩＋参考图、透明输出、`xhigh/max`、批量、流式最终图；Sunburst 的 Responses 图片工具生成/改图也产出图片。但不同站、不同参数组合仍需各自验收。实际返回尺寸可能不同于请求，WebP 可能是本地对 PNG 的可靠转换，流式可能没有中间预览。原站的 File ID 上传和“仅凭 Response ID 续改”未打通；Flare 的 Responses 工具路径未独立实测。未声称已验证上游 C2PA 具体模型标识。

本项目与 OpenAI 无隶属或背书关系，型号名称仅标识协议兼容，不保证你的网关已开通。不要提交 Key、私有配置、输入图片或私人产物。

## 贡献、授权和来源

见 [CONTRIBUTING.md](CONTRIBUTING.md)。仓库代码使用 [Apache-2.0](LICENSE)；部分提示词和缩图辅助逻辑源自 Apache-2.0 授权的 OpenAI imagegen skill，见 [NOTICE](NOTICE)。OpenAI SDK 与 Pillow 依各自许可证。
