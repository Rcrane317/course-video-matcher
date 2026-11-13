# 课件网课匹配 / course-video-matcher

把一堆结构不明的大学课程课件压缩包，变成「第几章该看 B站 哪个视频」的对照表。

**核心约束**：只搜 B站 · 剔除广告卖课 · 只留免费且已更新完毕 · 逐条核验视频是否已被删除 · 合集优先 · 全部候选按匹配度排序。

## 它做什么

1. **解包清点**：zip / 7z / rar / tar.gz / 已解压目录，自动剥嵌套、分课程、解析 `第3章 / 第5讲 / L3.2`、按内容哈希去重。
2. **认定课程**：读课件首页判断课程名、教师、学校、教材版次——同名不同校是最大的坑。
3. **拆讲义序列**：每份讲义提炼 3–6 个可区分的关键词，作为后续匹配依据。
4. **检索**：先找整门课的完整合集，只有某讲确实没有合适合集时才补专题片段。
5. **核验**：逐条请求 B站 公开接口，确认没被删除、分P真实存在、确实免费，并核对站内标题与声称的是否一致。
6. **出表**：单文件 HTML，可筛选、可搜索，每条都是可点击链接，带匹配度与核验时间。

## 安装

```bash
/plugin marketplace add <你的用户名>/course-video-matcher
/plugin install course-video-matcher@cvm-skills
```

装好后对 AI 说「上传的这几个课件压缩包，帮我找 B站 对应的网课」即可触发。

## 五道门禁

| 门禁 | 判据 | 不过怎么办 |
|---|---|---|
| 平台 | 只认 `bilibili.com` / `b23.tv` | 丢弃 |
| 广告 | 标题/UP主命中引流词；简介命中强词 | 丢弃（简介只提网盘时保留并打标） |
| 付费 | `rights.pay` / 充电专属 | 丢弃 |
| 完整性 | 标「持续更新中」 | 丢弃 |
| 存活 | 接口 `-404` / 62002 / 分P不存在 / 标题对不上 | 丢弃并在表里说明原因 |

## 关于「核验」

B站 上的资源随时会下架，搜索摘要也看不出视频已经没了。所以每次运行都会：

```bash
python scripts/probe.py --candidates candidates.json --out probe.json
```

它会打 `https://api.bilibili.com/x/web-interface/view?bvid=<BV>`，一次拿到存活状态、分P列表、付费标记和真实标题。
**核验有时效性**，表里每条都标了核验时间；想复核某一条：

```bash
python scripts/probe.py --url "https://www.bilibili.com/video/BV..."
```

## 运行环境

- Python 3.9+，脚本全部零第三方依赖（pptx 直接解析 OOXML，xlsx 已废弃改为 HTML）
- `.7z` 需要 `py7zr`（缺失时脚本会提示安装）；`.rar` 需要本机有 7-Zip 或 WinRAR
- PDF 文本抽取依赖宿主环境的 `workbuddy-pdf`；没有时退化为按文件名推断，精度会下降

## 网络行为与隐私

只访问两类地址：

- `https://api.bilibili.com/x/web-interface/view` —— 核验视频是否可看
- 搜索工具所用的搜索引擎（由宿主提供）

不下载、不转存、不解析任何视频流；只读取公开的稿件元数据。所有中间产物都在本地工作目录。

## 目录

```text
.codebuddy-plugin/marketplace.json          市场清单
plugins/course-video-matcher/
├── .codebuddy-plugin/plugin.json           插件清单
└── skills/course-video-matcher/
    ├── SKILL.md                            技能说明（含完整执行流程）
    ├── scripts/{materials,probe,align,write_html}.py
    ├── references/{platforms,scoring}.md
    └── assets/                             候选集样例与输出样例
```

## 已知限制

- `.rar` 在没有解压工具的机器上解不开，需用户先手动解压
- 老式 `.ppt` 与扫描版 PDF 抽不出文字，只能靠文件名匹配
- 「是否已更新完毕」接口不直接返回，仍需结合标题与简介判断
- 冷门课或校内自编教材覆盖率会明显偏低，这是严格口径的必然结果

## License

MIT
