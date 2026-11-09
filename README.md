# ICJSearcher 部署指引

独立检索国际法院（ICJ）官网 Document Search，并读取判决/命令 PDF。只访问 `icj-cij.org`。

仓库：<https://github.com/HuiwowICCSkills/ICJSearcher>（公开）。

## 1. 环境

| 组件 | 要求 |
| --- | --- |
| Python | 3.10+，`requests`、`beautifulsoup4`、`pypdf` |
| 可选回退 | `requirements-bypass.txt` 中的 DrissionPage、curl_cffi、python-socks、psutil |
| 浏览器 | 可选回退需要 Chrome/Chromium/Edge；`search` 不需要 |

## 2. 安装

```powershell
git clone https://github.com/HuiwowICCSkills/ICJSearcher.git "$env:USERPROFILE\.codex\skills\ICJSearcher"
python -m pip install -r "$env:USERPROFILE\.codex\skills\ICJSearcher\requirements.txt"
# 需要 PDF 无头回退时再安装：
python -m pip install -r "$env:USERPROFILE\.codex\skills\ICJSearcher\requirements-bypass.txt"
```

## 3. 自检

```powershell
& "$env:USERPROFILE\.codex\skills\ICJSearcher\run.ps1" doctor
```

`doctor` 检查核心依赖、可选回退依赖和 Document Search。直接检索成功时，即使回退依赖未安装也可用；PDF 被 Cloudflare 403 时才需要回退。

## 4. 使用

```powershell
$icj = "$env:USERPROFILE\.codex\skills\ICJSearcher\run.ps1"
& $icj search 'state immunity' --limit 10 --out './icj.json'
& $icj fetch 'https://www.icj-cij.org/sites/default/files/case-related/...pdf' --pdf-out './icj.pdf' --text-out './icj.txt' --out './fetch.json'
```

## 5. 排错

| 现象 | 处理 |
| --- | --- |
| PDF 直链 403 | 确认已安装 `requirements-bypass.txt`，并设置 `ICJ_BROWSER_PATH` 或安装 Chrome |
| 回退超时 | `cloudflare_bypass.py` 需要启动浏览器；检查 Chrome 路径和网络 |
| `Insufficient ICJ page text` | 可能是访问页或 JS 壳；检查 URL 是否为案件页/PDF |
| `About N results` 与返回条数不一致 | `total` 是全站命中数，结果按页返回；用 `next_offset` 续页 |

## 6. 边界

本 skill 只做 ICJ 官网；其他法院/法庭用 `HUDOCSearcher`、`ICTYSearcher`、`ICTRSearcher`、`IRMCTCldSearcher`。检索结果是元数据，引用前必须读取 PDF 并核对案件、文书类型、日期和页码。

## 实测效果（2026-11-09）

以下命令与结果来自本机 `~/.codex/skills/ICJSearcher` 的实网运行；检索日期 2026-11-09（Asia/Shanghai），输出为该次运行实际返回的 JSON 报告。

```powershell
& .\run.ps1 search 'state immunity' --limit 5
```

- 状态：`ok`；服务端/索引报告 `total = 5869`；本次返回 5 条。
- 代表性结果：

| 题名 | 类型 / 日期 | 链接 |
| --- | --- | --- |
| The Court to deliver its Judgment on Thursday 19 November 2026 at 10 a.m. | Press releases；2026-11-03 | https://www.icj-cij.org/sites/default/files/case-related/178/178-20261103-pre-01-00-en.pdf |
| Colombia withdraws its Declaration of intervention in the proceedings | Press releases；2026-09-22 | https://www.icj-cij.org/sites/default/files/case-related/192/192-20260922-pre-01-00-en.pdf |
| Written comments of Germany on the reply of Nicaragua  to the question put by Judge Charlesworth | Other documents；2026-09-22 | https://www.icj-cij.org/sites/default/files/case-related/193/193-20260922-oth-01-00-en.pdf |

> 说明：`total = 5869` 是 ICJ 全站 Document Search 对 `state immunity` 的命中总数（`scope`：Official ICJ Document Search across case-related documents），覆盖新闻稿、其他案件文书和书状，并按日期倒序排列，因此前几条是 2026 年的新闻稿与其他文书，而不是精确的"国家豁免"判例命中；判断相关性必须结合命中语境而非关键词。结果行是官方检索记录的元数据（`result_type = retrieved_metadata`，`content_scope`：official ICJ Document Search record, not the judgment text），PDF 正文须用 `fetch` 另行抓取并核对案件、文书类型、日期和页码。