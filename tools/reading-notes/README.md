# 每周公开读书笔记周报自动化

这个目录配合 `.github/workflows/weekly-reading-notes.yml` 使用，每周一北京时间 08:00 自动从公开线上来源收集别人发布的读书笔记，并输出到 `reports/reading-notes/`。

## GitHub Variables 配置

在 GitHub 仓库的 `Settings -> Secrets and variables -> Actions -> Variables` 中添加：

- `READING_NOTE_SOURCES_JSON`：必填，公开读书笔记来源配置。

`READING_NOTE_SOURCES_JSON` 示例：

```json
[
  {
    "name": "豆瓣公开读书笔记",
    "type": "html",
    "url": "https://www.douban.com/group/topic/示例公开帖子ID/"
  },
  {
    "name": "读书博客 RSS",
    "type": "rss",
    "url": "https://example.com/feed.xml"
  },
  {
    "name": "整理好的公开读书笔记源",
    "type": "json",
    "url": "https://example.com/public-reading-notes.json"
  }
]
```

## 可选 Secrets 配置

默认建议只采集公开页面、RSS 或公开 JSON，不使用个人账号 Cookie。

如果某个来源是你被授权访问的半公开页面，可以在来源配置里显式指定 Cookie 环境变量：

```json
[
  {
    "name": "授权访问的读书笔记页面",
    "type": "html",
    "url": "https://example.com/notes",
    "cookieEnv": "CUSTOM_SOURCE_COOKIE"
  }
]
```

然后在 `Settings -> Secrets and variables -> Actions -> Secrets` 中添加：

- `CUSTOM_SOURCE_COOKIE`

不要用这个自动化绕过平台权限、抓取私密内容或批量复制受版权保护的全文。

## 来源格式

当前支持三类来源：

- `html`：抓取公开网页，并从页面文本中提取笔记片段。
- `rss`：抓取公开 RSS/Atom 订阅源。
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
