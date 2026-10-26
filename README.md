# Astro 班级知识库阅读助手

让你的 Agent 帮你找课件、读原文、取资源，并给出能核对的出处。Skill 与 Chrome/Edge 阅读插件共用本仓库，无须部署云服务器。

## 复制这一句话给 Agent

> 请读取 https://raw.githubusercontent.com/caiwu557-ai/astro-class-kb/main/INSTALL.md ，按其中流程为我安装并配置班级知识库阅读助手。优先使用你已有的浏览器；需要插件时再部署。检查下载来源，修改已有配置前备份，遇到需要我点击或授权的步骤集中告诉我。完成后打开知识库、查找一份课件并给出带出处的结果。

已有浏览器工具的 Agent 通常直接就能用，不必装插件。只有纯对话、不能浏览或操作本机的 Agent 无法仅靠一句话完成部署。

- [从这里安装](INSTALL.md)
- [Skill 完整流程](skills/astro-class-kb/SKILL.md)
- [插件与本机 MCP 配置](browser-bridge/README.md)
- [下载固定版本与 SHA-256 清单](https://github.com/caiwu557-ai/astro-class-kb/releases)
- [公开知识库首页](https://xcnmfu3da215.feishu.cn/wiki/U8U0wMHFVipDpNkXPs6cCbsgn3e)
- [知识库内的使用入口](https://xcnmfu3da215.feishu.cn/wiki/EZF0wTqa0ixDtakdG0Vc4mcZnVd)

## 装好后这样用

“找感染与免疫里补体相关的中英文课件，阅读后解释，并标出 PDF 页序和原链接。”

“找 Urinary system.pdf，给我原文件入口；我确认需要下载后再保存。”

“阅读首页开发者的话，告诉我怎样参与共建。”

## 内容与边界

`skills/astro-class-kb/` 包含阅读指令、公开目录和带日期的检索快照。`browser-bridge/` 包含可选浏览器扩展和纯 Python 标准库 MCP 桥。课件原文件、后台管理工具、私有收件表、邮件、账号凭证和内部协作交接均不在仓库中。

PDF/PPT 的关键词只用于定位，回答前须读原文或看对应页面。快照日期见 `coverage.json`，在线最新版以知识库为准。资料公开可读不代表课件版权已转让，也不代表可以任意再分发。

插件为独立实现，只声明 activeTab、scripting、storage，主机限知识库域名和本机回环地址；没有复制 OpenAI 插件源码。安装说明不会要求关闭浏览器安全检查。

## 验证状态

11 项离线/模拟测试通过；公开网页读取、PDF 与 Skill 下载做过实际核验。自制插件尚未在真实 Chrome/Edge 和 Agent MCP 客户端联合安装验收，因此首版是可下载的试用版本，不宣称一键部署已在所有客户端验证。

## 运行测试

Python 3.10+，无第三方 Python 依赖。JavaScript 测试需要已有 Node.js：

```text
python -m unittest discover -s . -p test_reader.py
python -m unittest discover -s browser-bridge -p test_bridge.py
node --test browser-bridge/test-core.mjs
```

浏览器安装和客户端配置保持用户可见；仓库不安装后台服务、不改系统 PATH、不设置定时任务。
