# 课件网课匹配 / course-video-matcher

把一堆结构不明的大学课程课件压缩包，变成「第几章该看 B站 哪个视频」的对照表。

**核心约束**：只搜 B站 · 剔除广告卖课 · 只留免费且已更新完毕 · 逐条核验视频是否已被删除 · 合集优先 · 全部候选按匹配度排序 · 支持「全程网课 / 突击网课」双模式。

**v3.0 起为通用版**：不再绑定任何单一 agent 平台。仓库根目录就是标准 [Agent Skills](https://agentskills.io) 布局（`SKILL.md` + 脚本），另附 MCP 服务器，四种用法随选。

## 它做什么

1. **解包清点**：zip / 7z / rar / tar.gz / 已解压目录，自动剥嵌套、分课程、解析 `第3章 / 第5讲 / L3.2`、按内容哈希去重。
2. **认定课程**：读课件首页判断课程名、教师、学校、教材版次——同名不同校是最大的坑。
3. **拆讲义序列**：每份讲义提炼 3–6 个可区分的关键词，作为后续匹配依据。
4. **检索**：先找整门课的完整合集，只有某讲确实没有合适合集时才补专题片段。
5. **核验**：逐条请求 B站 公开接口，确认没被删除、分P真实存在、确实免费，并核对站内标题与声称的是否一致。
6. **出表**：单文件 HTML，可筛选、可搜索，每条都是可点击链接，带匹配度与核验时间。

## 四种使用方式

### 方式一：Agent Skill（Claude Code / 任何支持 SKILL.md 规范的 agent）

```bash
# Claude Code：把仓库克隆到本地，指向项目或用户级 skills 目录
git clone https://github.com/Rcrane317/course-video-matcher.git
# 放进 ~/.claude/skills/course-video-matcher（用户级）
# 或 <项目>/.claude/skills/course-video-matcher（项目级）
```

之后对 agent 说「上传的这几个课件压缩包，帮我找 B站 对应的网课」即可触发。其它兼容 Agent Skills 规范的环境（OpenCode、Amp 等）同理：整个目录放进 skills 搜索路径即可。

### 方式二：MCP 服务器（Claude Desktop / Cursor / Cline / Windsurf 等）

```bash
pip install "mcp[cli]"
python mcp_server.py        # stdio 传输
```

客户端 `mcpServers` 配置（各家通用写法）：

```json
{
  "mcpServers": {
    "course-video-matcher": {
      "command": "python",
      "args": ["/绝对路径/course-video-matcher/mcp_server.py"]
    }
  }
}
```

暴露的 MCP 工具：

| 工具 | 对应流水线阶段 | 作用 |
|---|---|---|
| `unpack_materials` | Phase 0 | 解包压缩包、分课程、抽章节序号 |
| `validate_candidates` | Phase 4 | 校验 agent 写好的 candidates.json |
| `probe_links` | Phase 5 | 逐条核验 B站 链接是否在播 |
| `align_and_rank` | Phase 6 | 过滤、打分、按匹配度排序 |
| `render_report` | Phase 7 | 渲染单文件 HTML 对照表 |
| `probe_single_url` | 调试 | 单测一条链接 |

检索与 candidates.json 的语义判断由客户端 agent 按 `SKILL.md` 的 Phase 1–4 完成，再送回流水线。

### 方式三：纯 CLI（不用 agent）

```bash
python scripts/materials.py <课件压缩包或文件夹> --out 网课匹配_20261113
python scripts/probe.py     --candidates candidates.json --out probe.json
python scripts/align.py     --materials materials.json --candidates candidates.json \
                            --probe probe.json --mode full --out alignment.json
python scripts/write_html.py alignment.json -o 网课对照表.html
```

`candidates.json` 的撰写与 B站 检索属语义工作，格式见 `assets/candidates.example.json`，打分锚点见 `references/scoring.md`。

### 方式四：CodeBuddy / WorkBuddy 插件市场

```bash
/plugin marketplace add Rcrane317/course-video-matcher
/plugin install course-video-matcher@cvm-skills
```

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

- Python 3.8+，核心脚本零第三方依赖（pptx 直接解析 OOXML，xlsx 已废弃改为 HTML）
- `.7z` 需要 `py7zr`（缺失时脚本会提示安装）；`.rar` 需要本机有 7-Zip 或 WinRAR
- PDF 文本抽取优先用 `pdftotext`（poppler-utils，`apt install poppler-utils` / `brew install poppler` / `winget install poppler`），也兼容 WorkBuddy 的 `workbuddy-pdf` CLI；都没有时退化为按文件名推断，精度会下降
- MCP 模式额外需要 `pip install "mcp[cli]"`

## 网络行为与隐私

只访问两类地址：

- `https://api.bilibili.com/x/web-interface/view` —— 核验视频是否可看
- 搜索工具所用的搜索引擎（由宿主提供）

不下载、不转存、不解析任何视频流；只读取公开的稿件元数据。所有中间产物都在本地工作目录。

## 目录

```text
SKILL.md                                技能说明（开放 Agent Skills 格式，含完整执行流程）
mcp_server.py                           MCP 服务器（六个工具，覆盖全部流水线）
requirements.txt                        可选依赖说明
scripts/{materials,probe,align,write_html}.py
references/{platforms,scoring}.md
assets/                                 候选集样例与输出样例
.codebuddy-plugin/marketplace.json      插件市场清单
plugins/course-video-matcher/           插件市场打包（与根目录同内容）
```

## 已知限制

- `.rar` 在没有解压工具的机器上解不开，需用户先手动解压
- 老式 `.ppt` 与扫描版 PDF 抽不出文字，只能靠文件名匹配
- 「是否已更新完毕」接口不直接返回，仍需结合标题与简介判断
- 冷门课或校内自编教材覆盖率会明显偏低，这是严格口径的必然结果

## License

MIT
