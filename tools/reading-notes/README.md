# 每周读书笔记周报自动化

这个目录配合 `.github/workflows/weekly-reading-notes.yml` 使用，每周一北京时间 08:00 自动从配置的线上来源拉取读书笔记，并输出到 `reports/reading-notes/`。

## GitHub Secrets 配置

在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions` 中添加：

- `READING_NOTE_SOURCES_JSON`：必填，读书笔记来源配置。
- `DOUBAN_COOKIE`：选填，豆瓣私密页面需要登录态时使用。
- `WEREAD_COOKIE`：选填，微信读书私密页面或导出接口需要登录态时使用。

`READING_NOTE_SOURCES_JSON` 示例：

```json
[
  {
    "name": "豆瓣",
    "type": "html",
    "url": "https://www.douban.com/people/你的豆瓣ID/notes"
  },
  {
    "name": "微信读书导出",
    "type": "json",
    "url": "https://example.com/weread-notes.json"
  }
]
```

## 来源格式

当前支持两类来源：

- `html`：抓取公开或带 Cookie 可访问的网页，并从页面文本中提取笔记片段。
- `json`：抓取 JSON 数据，支持数组格式，或 `{ "notes": [] }` 格式。

JSON 笔记字段建议包含：

```json
{
  "bookName": "书名",
  "content": "笔记内容",
  "createdAt": "2026-06-30",
  "url": "原文链接"
}
```

## 输出

每次运行会生成当周 Markdown 周报：

```text
reports/reading-notes/YYYY-Www.md
```

工作流会同时把周报作为 GitHub Actions artifact 上传，并提交回仓库。
