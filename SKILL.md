---
name: ICJSearcher
description: 独立检索国际法院（ICJ）官网 Document Search，查找案件相关判决、命令、书状、新闻稿和其他官方文件；支持 PDF 下载、逐页文本提取，以及 Cloudflare 挑战时的无头 Chrome 回退。
---

# ICJSearcher

> **`<skill-dir>`** = 本 SKILL.md 所在目录。核心脚本为 `<skill-dir>/scripts/icj_search.py`；Windows 用 `<skill-dir>/run.ps1`，macOS/Linux 用 `<skill-dir>/run.sh`。部署与排错见 [README.md](README.md)。

这个 skill 只做 `icj-cij.org` 一个站点：

- `search`：调用 ICJ 官方 `advanced-search` 的 `search_api_fulltext`，返回文书题名、案件、文书类型、日期和具体 PDF 链接；
- `fetch`：按返回的 PDF/HTML URL 下载并提取逐页文本；PDF 直链遇 Cloudflare 403/挑战页时，自动调用仓库内 vendored 的无头浏览器回退；
- `doctor`：检查 Python、解析依赖、可选的无头回退依赖，并探测 Document Search。

## 命令

```powershell
# 官方 Document Search
& '<skill-dir>/run.ps1' search 'state immunity' --limit 10 --out './icj-search.json'

# Advanced Search：精确短语 + 文书类型 + 日期范围
& '<skill-dir>/run.ps1' search 'immunity' --phrase 'state immunity' --document-type judgments --date-from 2010-01-01 --date-to 2020-12-31 --limit 5

# 附带程序 + 案件 id（案件 id 可在 Advanced Search 的 Case(s) 下拉框中查看）
& '<skill-dir>/run.ps1' search 'provisional measures' --incidental 'Provisional measures' --case-id 5001 --limit 5

# 取判决/命令 PDF，保存 PDF 与带 @@PAGE n@@ 标记的文本
& '<skill-dir>/run.ps1' fetch 'https://www.icj-cij.org/sites/default/files/case-related/...pdf' --pdf-out './icj.pdf' --text-out './icj.txt' --out './icj-fetch.json'

# 取案件页 HTML
& '<skill-dir>/run.ps1' fetch 'https://www.icj-cij.org/case/178' --out './icj-case.json'

# 部署自检
& '<skill-dir>/run.ps1' doctor
```

通用参数：`--out`、`--cache`、`--cache-ttl`、`--offline`、`--timeout`。`search` 另有 `--limit`、`--offset`、`--phrase`、`--wildcard`、`--document-type`、`--incidental`、`--date-from`、`--date-to`、`--sort`、`--case-id`；`fetch` 另有 `--pdf-out`、`--text-out`、`--max-mb`。

## 结果边界

- `search` 的结果是**官方检索元数据**，不是判决正文；`fulltext_url` 指向具体 PDF，仍需 `fetch` 才能取得文本。
- `--phrase` 对应 ICJ Advanced Search 的 `search_api_fulltext_1`（this exact word or phrase），`--wildcard` 对应 `search_api_fulltext_2`，普通 query 对应 `search_api_fulltext`（any of these words）。`--document-type` 可用 ID（如 `486`）或标签（如 `Judgments`），`--incidental` 可用 ID（如 `409`）或标签（如 `Provisional measures`）；完整 ID 表和日期过滤参数见 [references/icj-search.md](references/icj-search.md)。
- `fetch` 的 PDF 文本页号是 PDF 位置（`@@PAGE n@@`），不是印刷页码；扫描件可能出现 `needs_ocr=true`。
- ICJ 网站对 PDF 直链可能返回 Cloudflare 403；`fetch` 会自动使用 `scripts/cloudflare_bypass.py` 和 `scripts/vendor/CloudflareBypassForScraping`。该回退需要 `requirements-bypass.txt` 中的依赖；只做 `search` 时不需要。
- `search` 结果是全站 Document Search，可能含新闻稿、其他文件与不同案件；引用前核对案件名、文书类型、日期和 PDF 内容，不要只凭标题。
- 单次 403/挑战页不等于资料不存在；先看 `doctor` 和 `warnings`，不要对同一请求反复探测。

## 参考

- 2026-11-09 实测：Document Search 参数、结果选择器、PDF 403 与无头回退：[references/icj-search.md](references/icj-search.md)
- 部署、环境与排错：[README.md](README.md)
