# Third-party notices

本目录有两份改编技能，来自 [ECC](https://github.com/affaan-m/ECC) `d3b8a3e908904e242ed2dbe66af62cca71131419`（短名 `d3b8a3e`）。许可证为 MIT，版权行：`Copyright (c) 2026 Affaan Mustafa`。

| 技能 | 路径 | 来源 | 改动 |
|---|---|---|---|
| strategic-compact | `.cursor/skills/strategic-compact/SKILL.md` | `skills/strategic-compact/SKILL.md` | 改编。保留阶段切换、压缩前把计划写入文件、重复指令检测。删去 Claude Code 的 hook、`/compact`、版本说明和 MCP 推荐。收尾改为把状态写入 `docs/` 或任务文件后开新会话。 |
| context-budget | `.cursor/skills/context-budget/SKILL.md` | `skills/context-budget/SKILL.md` | 改编。盘点对象改为 `.cursor/skills`、`.cursor/rules`、各级 `AGENTS.md` / `CLAUDE.md`、`.cursor/mcp.json`。阈值仍是：单个技能超过 400 行、单条规则超过 100 行、AGENTS 链超过 300 行、MCP 超过 10 个服务器或 20 个工具。设置 `disable-model-invocation: true`，只在手动 `/context-budget` 时加载。 |

未复制 ECC 的其他技能、hook 或 agent。

## ECC MIT License

```
MIT License

Copyright (c) 2026 Affaan Mustafa

Permission is hereby granted, free of charge, to any person obtaining a copy
of this software and associated documentation files (the "Software"), to deal
in the Software without restriction, including without limitation the rights
to use, copy, modify, merge, publish, distribute, sublicense, and/or sell
copies of the Software, and to permit persons to whom the Software is
furnished to do so, subject to the following conditions:

The above copyright notice and this permission notice shall be included in all
copies or substantial portions of the Software.

THE SOFTWARE IS PROVIDED "AS IS", WITHOUT WARRANTY OF ANY KIND, EXPRESS OR
IMPLIED, INCLUDING BUT NOT LIMITED TO THE WARRANTIES OF MERCHANTABILITY,
FITNESS FOR A PARTICULAR PURPOSE AND NONINFRINGEMENT. IN NO EVENT SHALL THE
AUTHORS OR COPYRIGHT HOLDERS BE LIABLE FOR ANY CLAIM, DAMAGES OR OTHER
LIABILITY, WHETHER IN AN ACTION OF CONTRACT, TORT OR OTHERWISE, ARISING FROM,
OUT OF OR IN CONNECTION WITH THE SOFTWARE OR THE USE OR OTHER DEALINGS IN THE
SOFTWARE.
```
