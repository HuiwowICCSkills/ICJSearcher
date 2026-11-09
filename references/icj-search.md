# ICJ 检索实测记录（2026-11-09）

## Document Search

`https://www.icj-cij.org/advanced-search`

参数：`search_api_fulltext`、`items_per_page`、`page`（0 起）。

请求头：Chrome/156 UA。

结果容器：`.view-document-search`；总数：`.view-header` 中的 `About N results`；行：`.view-content .views-row`；标题链接：`h4 a[href]`。

实测 `state immunity --limit 2` → `status=ok`、`total=5869`、2 条；结果是全站 Document Search，可能含新闻稿和其他文件。

## PDF

`https://www.icj-cij.org/sites/default/files/case-related/178/178-20261103-pre-01-00-en.pdf`

- 直接 `requests` + 浏览器 UA → HTTP 403（Cloudflare HTML）
- `scripts/cloudflare_bypass.py`（vendored CloudflareBypassForScraping）→ HTTP 200、310,168 字节、PDF 签名有效、4 页、`needs_ocr=false`，耗时约 24.6 秒
- 回退需要 `requirements-bypass.txt` 中的 DrissionPage/curl_cffi 等依赖

## 边界

- `search` 的行是元数据，不是判决正文；`fulltext_url` 仍需 `fetch`。
- PDF 页号是 PDF 位置，不是印刷页码。
- 回退失败时保留直接失败证据和错误，不把 403 当作“没有资料”。
