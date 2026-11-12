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

## Advanced Search 字段（2026-11-12 浏览器核对）

页面：`https://www.icj-cij.org/advanced-search`，GET 表单。字段：

| 参数 | 界面标签 | 取值 |
| --- | --- | --- |
| `search_api_fulltext` | any of these words | 任意关键词 |
| `search_api_fulltext_1` | this exact word or phrase | 精确短语 |
| `search_api_fulltext_2` | this wildcard term | 通配词 |
| `case_selection` | Case(s) | `1`=all cases，`2`=selected cases |
| `field_doc_case_code_1[]` | selected cases | 案件数字 id，如 `5001`；可多值 |
| `field_document_group_type` | Document type | `All` 或 477–497（见下表） |
| `field_doc_incidental_proceedings` | Incidental proceedings | `All` 或 409–414 |
| `field_date_of_the_document[min]` / `[max]` | Document date | `YYYY-MM-DD` |
| `items_per_page` | Items per page | 10/25/50/100 |
| `sort_order` | Sort | `ASC` / `DESC`（默认 DESC） |

Document type 关键值：`477` Application，`478` Special agreement，`479` Request for Advisory Opinion，`480` Written proceedings，`481` Other documents，`482` Oral proceedings，`483` Orders，`486` Judgments，`489` Advisory opinions，`495` Summaries，`496` Press releases，`497` Correspondence。

Incidental proceedings：`409` Provisional measures，`410` Preliminary objections，`411` Counter-claims，`412` Intervention，`413` Questions of jurisdiction and/or admissibility，`414` Discontinuance。

实测：只用 `search_api_fulltext_1=state immunity` + `field_document_group_type=486` + `2010-01-01..2020-12-31` → 4 条；再加上 `search_api_fulltext=immunity`（any-of-words）→ 7 条。作为对照，`search_api_fulltext=state immunity` 不限类型/日期为 5,869 条，说明短语、类型和日期过滤确实生效。
