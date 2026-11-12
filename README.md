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

## 实测效果（2026-11-12）

以下命令与结果来自本机 `~/.codex/skills/ICJSearcher` 的实网运行；检索日期 2026-11-12（Asia/Shanghai），输出为该次运行实际返回的 JSON 报告。

```powershell
$icj = "$env:USERPROFILE\.codex\skills\ICJSearcher\run.ps1"
& $icj search 'immunity' --phrase 'state immunity' --document-type judgments --date-from 2010-01-01 --date-to 2020-12-31 --limit 5
```

- 状态：`ok`；`total = 7`；本次返回 5 条。
- 高级过滤：`search_api_fulltext=immunity`（any-of-words）、`search_api_fulltext_1=state immunity`（exact phrase）、`field_document_group_type=486`（Judgments）、`field_date_of_the_document[min/max]`。
- 代表性结果：

| 文书 | 案件 | 类型 / 日期 | PDF |
| --- | --- | --- | --- |
| Judgment of 11 December 2020 | Immunities and Criminal Proceedings (Equatorial Guinea v. France) | Judgments；2020-12-11 | https://www.icj-cij.org/sites/default/files/case-related/163/163-20201211-JUD-01-00-EN.pdf |
| Judgment of 13 February 2019 | Certain Iranian Assets (Islamic Republic of Iran v. United States of America) | Judgments；2019-02-13 | https://www.icj-cij.org/sites/default/files/case-related/164/164-20190213-JUD-01-00-EN.pdf |
| Judgment of 6 June 2018 | Immunities and Criminal Proceedings (Equatorial Guinea v. France) | Judgments；2018-06-06 | https://www.icj-cij.org/sites/default/files/case-related/163/163-20180606-JUD-01-00-EN.pdf |

> 说明：以上是 ICJ Document Search 的**检索元数据**，不是判决正文；`fulltext_url` 仍需用 `fetch` 下载并核对实际文本、日期、案件号和页码。
