---
name: course-video-matcher
description: "Match an uploaded pile of university lecture decks (PPT/PDF inside zip/7z/rar archives, often several courses at once) to real Bilibili course videos. Scope is locked to bilibili.com; ads and paid-course funnels are filtered out, only free and fully-published series are kept, every link is probed against Bilibili's public API so deleted or missing-part videos are dropped, complete playlists are preferred over single-topic clips, every qualifying candidate is listed by descending match score, and a full-course vs. crash-course mode switches what counts as a good match."
license: MIT
metadata:
  display_name: "课件网课匹配"
  display_name_en: "Course Deck to Bilibili Course Matcher"
  description_zh: "用户上传大学课程 PPT/PDF 压缩包合集后，自动解包、识别课程与章节目录，只在 B站 检索对应网课：支持全程网课与突击网课两种模式，按视频标题关键词归类；剔除广告卖课、只留免费且已更新完毕的，逐条核验是否已被删除、分P是否存在、实际是否付费，按匹配度从高到低列出全部候选，产出带可点击链接的单文件 HTML。"
  description_en: "Unpack lecture-deck archives and search Bilibili only for free, fully-published series. Two selectable modes - full course vs. crash course - change both the query set and the score weighting. Ad-driven clips are filtered, every link is probed against Bilibili's public API, and all candidates are ranked in a self-contained HTML report."
  category: "education"
  version: "2.3.0"
---

# 课件网课匹配（B站版）

把「一堆看不清结构的课件压缩包」变成「第几章该看哪个视频、链接在哪、还有哪些备选、这条有多可信」。

## 硬口径（用户已明确要求，不能自行放宽）

| 项   | 规则                                         |
| --- | ------------------------------------------ |
| 平台  | **只搜 bilibili.com**。其他平台的链接一律不收录，哪怕匹配度更高   |
| 广告  | 标题/UP主/简介含卖课引流词的整条丢弃，见下方词表                 |
| 付费  | 只收免费可看；需付费、需购课、需加群才给资源的，丢弃                 |
| 完整性 | 只收**已更新完毕**的合集；「持续更新中」「未完待续」的丢弃            |
| 优先级 | **先找完整合集**；某一讲确实没有合适合集时，才去搜专题片段补点          |
| 存活  | **只收此刻还能看的**：逐条请求 B站 稿件接口确认。已删除、私密/审核中、分P不存在、实际付费、标题与站内对不上的，一律剔除 |
| 模式  | 先确认用户要**全程网课**（系统学完）还是**突击网课**（考前速通）。归类以**标题关键词**为准，体量只做兜底。没说就默认全程 |
| 排序  | 每讲按匹配度**从高到低列出全部符合条件的候选**，让用户自己选，不做只给一个的截断 |
| 产物  | 单个自包含 HTML，所有推荐项都是可点击的 B站 链接，并标注核验时间        |

广告词分两档（`scripts/align.py` 内置，可用 `--ad-keywords` 覆盖）：

- **强词**（标题/UP主/简介任一命中即丢）：`扫码 / 私信 / 加微信 / 加V / vx / 微信 / QQ群 / 领取 / 获取 / 报名 / 咨询 / 一对一 / 1对1 / 保过 / 包过 / 押题 / 内部资料 / 辅导班 / 培训班 / 滴滴我 / 评论区 / 简介 / 购买 / 拼课 / 代看 / 代刷`
- **弱词**（只在标题/UP主命中才丢）：`资料包 / 网盘 / 提取码`。放在简介里不丢——大量正经免费课把课件传网盘，一律枪毙会误伤，只打一个提示标签。

脚本只查标题、UP 主名、简介正文——**不查你写的 note**，因为 note 里常有「简介没写章节」这类说明，会被自己误伤。

## 两种模式

同一批课件，两种人要的东西正好相反。开始干活前先定模式，因为它会改变**检索词**和**评分权重**。

| | 全程网课 `full`（默认） | 突击网课 `crash` |
|---|---|---|
| 给谁 | 想从头系统学完这门课 | 考前/临时抱佛脚，只要框架和考点 |
| 体量 | 只在标题看不出形态时参考：越长、集数越多越偏全程 | 同上，越短越偏突击 |
| 检索词 | `完整版` `全集` `课堂录播` `系统课` `零基础` | `速成` `期末突击` `考前串讲` `3小时` `考点总结` `一节课过完` |
| 覆盖 | **大部分章节覆盖即可**，不要求讲到课件最后一章 | **允许覆盖不全**，抓主干即可 |
| 评分 | 标题含全程词 → +24 分；含突击词 → −24 分 | 反过来 |

**判定顺序（权重从高到低，脚本按这个走）**

1. 标题（含分P名）出现 `突击 / 速成 / 期末 / 考前 / 冲刺 / 串讲 / 考点 / 复习 / 救命 / 速通 / 浓缩 / 划重点 / 总结 / N小时` → **整条归到突击网课**，哪怕它有 40 小时
2. 标题出现 `完整版 / 全集 / 全程 / 系统 / 课堂 / 录播 / 详解 / 逐章 / 配套教材 / 零基础` → **整条归到全程网课**，哪怕它只有 2 小时
3. 标题两类都没有（或同时出现，视为矛盾）→ 才看体量：整门 ≥15 小时且集数 ≥20 偏全程，≤3 小时或 1 集偏突击；这项只影响 ±10 分，不足以翻盘

一句话：**先看标题，标题说了算；标题没说，才用时长度量。**

几条实现细节（`--mode` 传给 `align.py`，脚本算，不用你估）：

- **只看标题，不看简介**。简介里常有「期末复习资料」「考点」这类无关表述，拿它判定会把整门系统课误判成突击课
- 标题同时含两类词（如「期末精讲」）视为矛盾，退回体量判断
- 体量 = `series.total_minutes`，没填则 `episodes × 单集时长`
- 模式只影响排序分（关键词 ±24，体量 ±10），**不影响五道门禁**——B站、免费、完结、无广告、未删除，两种模式一样严

怎么定模式：用户说「突击 / 速成 / 期末 / 考前 / 时间紧」→ `crash`；说「系统学 / 从头学 / 跟着学完」→ `full`；**没说就默认 `full`**，交付时补一句「如果只是想考前过一遍，我可以再出一版突击版」。

## 不做的事

- 不下载、不转存、不搬运；只给公开播放页链接。
- 不编造 BV 号、分P号、集数。没搜到就写「未找到」，比错链接有价值。
- **默认不给「第几分钟」时间戳**：那需要字幕或分段时间轴作为证据。只有打开过页面且页面确实有分段时间轴时才写，否则只到「第几集 / 哪个分P」。

## 交付物

工作区建 `网课匹配_<YYYYMMDD>/`：

| 文件                | 内容                               | 谁生成             |
| ----------------- | -------------------------------- | --------------- |
| `materials.json`  | 解包结果、课程分组、每份讲义的章/节/讲序号与标题线索、重复文件 | `materials.py`  |
| `candidates.json` | 检索到的 B站 系列与逐讲候选（**必须真实抓取**）      | agent 手写        |
| `probe.json`      | 每条链接的存活核验结果：可看 / 已删除 / 分P不存在 / 付费 / 标题不符 | `probe.py`      |
| `alignment.json`  | 过滤统计、打分、多候选排序、覆盖率                | `align.py`      |
| `网课对照表.html`      | **主交付物**：单文件，可筛选、可点击、含全部候选       | `write_html.py` |
| `匹配报告.md`         | 结论、推荐路径、可信度、缺失清单与替代方案            | agent 手写        |

## 执行流程

```bash
SKILL=~/.workbuddy/skills/course-video-matcher   # Windows: C:\Users\<你>\.workbuddy\skills\course-video-matcher
```

### Phase 0　解包与清点

```bash
python "$SKILL/scripts/materials.py" "<压缩包或文件夹>" --out "网课匹配_20261113"
```

支持 `.zip`（标准库）/ `.7z`（自动装 py7zr）/ `.rar`（找 7-Zip 或 WinRAR）/ `.tar.gz` / 已解压文件夹（`--no-unpack`）。会自动剥嵌套目录、按顶层目录分课程、抽 `第3章 / 3.2 / 第5讲 / L07` 序号、按内容哈希去重。

先看打印出来的分组对不对；分组错了就 `--no-unpack` 指向具体子目录重跑。`.rar` 解不开是常见情况（本机无解压工具），直接请用户手动解压后给文件夹路径。

### Phase 1　认定课程身份

读 `materials.json` 的 `name_guess` / `signals`，再翻 2–3 份首讲的 `slide_titles`、`text_head`（已在 JSON 里，别去读原文件），确定：课程全名、教师、学校、教材与版次、课程类型。

这几个信号直接决定 B站 上能不能搜准：

- 「本科正课 / 考研辅导 / 期末速成 / 实验课」属于哪类——B站 同一门课这四类的视频混在一起。
- 同名不同校：几乎每所学校都有「数据结构」「操作系统」，学校名往往就是唯一区分点。
- 教材版次：严蔚敏《数据结构》第 2 版与第 3 版章号不同，只能按知识点对齐。

`method` 为 `filename_only`（老 `.ppt`、扫描版 PDF）时，要明确告诉用户「只有文件名可用，精度会降」，并请其确认课程名。

### Phase 2　拆讲义序列

为每份讲义写 `lecture_label` 和 `topics`（3–6 个关键词）：

- `topics` 要用**能区分章节的名词**：`栈、队列、LIFO、FIFO`，不要写「概念、原理、概述」。
- 一章被切成 5 份 PPT 时，每份 topics 要不同，不要复制。
- 目录页、封面页不单独成条。

### Phase 3　检索：先合集，后片段

**Stage A｜找合集（必做，且优先）**

用域名限定把结果锁在 B站（`allowed_domains: ["bilibili.com"]`）。检索式**按模式分两套**，别混着搜：

**全程模式（`full`）**

- `{课程名} 完整版` / `{课程名} 全集` / `{课程名} 课堂录播`
- `{课程名} {学校}` / `{课程名} {教师}`（找同源正课）
- `{教材名} 配套课程`

**突击模式（`crash`）**

- `{课程名} 速成` / `{课程名} 期末突击` / `{课程名} 考前串讲`
- `{课程名} 3小时` / `{课程名} 一节课`
- `{课程名} 考点总结` / `{课程名} 思维导图 讲解`

突击模式下**多找几条短系列**再比：同一门课常有 2 小时、5 小时、8 小时三个版本，选结构与课件最接近的那一条，而不是最短的那条。

对每个候选合集，打开播放列表页核实一次，填三个门禁字段：

| 字段         | 怎么判                                                                     |
| ---------- | ----------------------------------------------------------------------- |
| `free`     | 免费能看 → `true`；需付费/购课 → `false`；页面说「私信获取」「加群看完整版」→ 直接当广告丢弃；看不出来 → `null` |
| `status`   | 最后一集能正常播放且无「未完待续」→ `complete`；明确「持续更新」→ `updating`；判断不了 → `unknown`     |
| `episodes` | 分P数或合集集数，用于判断体量是否与课件相当                                                  |
| `total_minutes` | 可选。整门总时长（分钟），合集页面上有就填；不填则用 `episodes × 单集时长` 估算。**突击模式下这个字段直接决定排序，值得花十秒填准** |

**Stage B｜补专题片段（仅当某讲没有合格合集）**

只对 Stage A 里空缺的讲做，检索式 `{课程名} {知识点} 讲解` / `{知识点} {课程名} 分钟`。单集片段按 `kind: "snippet"` 记，其它门禁字段一样要填。

**每门课检索次数控制在 8 次以内**；合集确定后靠分P标题定位，不要再逐讲开页面。

平台细节、合集完整性判断、B站 反爬后的替代路径见 `references/platforms.md`。

### Phase 4　填 candidates.json

照 `assets/candidates.example.json` 写，注意：

- `series` 一处定义（含 `kind/free/status/episodes/official/desc`），`matches[].picks[]` 用 `series_id` 引用。
- 每讲把**找到的所有候选都填进去**（不只填一个），脚本会排序后全部输出到 HTML。
- `llm_score` 是你的语义判断，锚点见 `references/scoring.md`。
- `evidence`：打开过播放列表页填 `page`，只有搜索摘要填 `snippet`。

先校验：

```bash
python "$SKILL/scripts/align.py" --validate "网课匹配_20261113/candidates.json" \
       --materials "网课匹配_20261113/materials.json"
```

会挑出：非 B站 链接、讲义对不上、`series_id` 悬空、分数越界。

### Phase 5　在播核验（必做）

搜索摘要不会告诉你视频已经下架了。这一步逐条请求 B站 公开接口，确认「此刻还能不能看」，顺带把编造的 BV 号抓出来。

```bash
python "$SKILL/scripts/probe.py" --candidates ".../candidates.json" --out ".../probe.json"
```

判定与处置：

| 探测结果 | 含义 | 处置 |
|---|---|---|
| `alive` | 接口 code=0，分P存在，非付费 | 收录，卡片上标「✓ 已核实在播 · 时间」 |
| `dead` | `-404 啥都木有` / 62002 不可见 / 62004 审核中 | **剔除**，计入 `filters.dead` |
| `part_missing` | 稿件在，但 `?p=N` 超出实际分P数 | **剔除**（链接指错了集） |
| `paid` / `restricted` | `rights.pay` 为真，或充电专属 | **剔除**（实际看不了） |
| `mismatch` | 站内真实标题与 candidates 里写的标题毫无重叠 | **剔除**（大概率是编的 BV） |
| `blocked` | 接口被风控 / 网络失败 | 默认剔除；`--allow-unverified` 可保留但打「在播未核验」标 |

单测一条链接：`python "$SKILL/scripts/probe.py" --url "https://www.bilibili.com/video/BV..."`。

接口被封（连续 `-412`）时脚本会以退出码 2 提示「本次探测不可信」，此时不要硬跑，隔几分钟重试或改用浏览器打开抽查几条。

### Phase 6　过滤打分排序

```bash
python "$SKILL/scripts/align.py" --materials ".../materials.json" \
       --candidates ".../candidates.json" --probe ".../probe.json" \
       --mode full --out ".../alignment.json"      # 突击版改成 --mode crash
```

输出第一行会告诉你当前模式。**两种模式可以各出一份 HTML**（用不同文件名），让用户对比后自己选——这是最省事的“让用户自选”。

输出还会打印两本台账：

- **过滤台账**：广告 / 付费 / 未完结 / 非B站 / 低分各丢了几条。
- **在播台账**：已删除、标题不符、无法核验各有几条，保留了多少条已核实可播。

**看一眼台账再收工**：广告丢十几条说明检索词撞进了卖课池，该换词重搜；已删除丢一大批说明这批资源太旧，该找近两年的系列。

### Phase 7　出 HTML

```bash
python "$SKILL/scripts/write_html.py" ".../alignment.json" -o ".../网课对照表.html"
```

然后写 `匹配报告.md`，必须含：

1. **一句话结论**：几门课、几讲、覆盖多少、能不能直接用。
2. **推荐路径**：每门课跟哪个合集，大概多少小时；哪几讲要额外看片段。
3. **过滤台账**：写清「因广告/付费/未完结剔除了 N 条」**和**「因已删除/失效剔除了 N 条」，让用户知道不是没搜到。
4. **缺失清单 + 替代方案**：具体到「换什么词重搜」「看教材配套」「找同类课程替代」。
5. **核验时间**：说明这是什么时候核验的，B站 上的资源随时可能下架。

用 `present_files` 把 HTML 交给用户（HTML 会在预览面板直接打开）。

## 质量闸门

交付前逐条自检，缺一条就别说「完成」：

- [ ] 所有链接都是 bilibili.com / b23.tv，且在**本轮**搜索或抓取结果里真实出现过。
- [ ] **每条入表链接都跑过 `probe.py` 且结果是 `alive`**；`filters.dead` / `mismatch` / `unverified` 全部为 0（或已在报告里说明保留原因）。
- [ ] 广告条数为 0 才交付（`filters.ad` 若 > 0 是已剔除数，不影响交付，但要写进报告）。
- [ ] 没有任何 `updating` 状态的系列混进结果。
- [ ] 覆盖率 =（含合集 + 仅片段）/ 有效讲义数 ≥ 50%；低于此要在报告里写清原因。
- [ ] 每讲至少检查过「有没有合集可用」，没有才用片段补——不能一开始就撒网搜片段。
- [ ] 同一讲的多条候选按分数严格降序，且都带了「合集/片段」标签。
- [ ] 没写任何未经页面核实的时间戳或集数。
- [ ] 「未找到」的讲都给了具体替代方案，并说明是因为「没有」还是「有但已失效/付费」。
- [ ] 模式对得上用户的话：说「突击/期末/考前」就跑的 `crash`，否则 `full`；两种都出了的话文件名区分清楚。
- [ ] `full` 模式下首推的那个系列覆盖了**大部分**讲义（缺的几章能在报告里点名说明）；不要求讲到最后一章。
- [ ] `crash` 模式下首推的是标题明确冲刺向的系列；别把 40 集的系统课当首推。

## 常见坑

| 现象             | 原因             | 处理                                                   |
| -------------- | -------------- | ---------------------------------------------------- |
| 搜出来大半是卖课       | 检索词撞进考研机构池     | 换「{学校} {课程名} 课堂录播」「{课程名} 完整版 分P」；把 UP 主限定为高校/机构号     |
| 合集只有前几集免费      | 前几集试看、后面要购课    | `free` 填 `false`，直接丢弃；在报告里说明「该系列为试看+付费」              |
| 分P标题只有「第1集」    | UP 主没按章命名      | 只能靠 `evidence=page` 打开看开头，或降级为 `llm_score` 50–60 并标注 |
| 同一 BV 号对应多门课   | 合集型账号把课堆在一个投稿里 | 必须带 `?p=N` 定位；`kind` 仍算 `collection`，但要在 `desc` 写明   |
| 一门课 60 份讲义     | 每页单独导出         | 先合并到章级再对齐，否则 HTML 会长得没法看                             |
| 老 `.ppt` 抽不出文字 | 二进制格式          | 只能靠文件名；降低预期并告知用户                                     |
| probe 大面积 `blocked` | 接口触发风控（-412/-352） | 隔几分钟重跑；或 `--allow-unverified` 保留并明确标注「在播未核验」          |
| probe 报 `mismatch` 很多 | candidates 里的标题是凭印象写的 | 说明链接大概率编错，回搜索页重新取真实标题，别硬保留                           |
| 突击模式里全是 40 集系统课 | 检索词用了「完整版」 | 换「速成 / 期末突击 / 考点总结」，并把 `total_minutes` 填准，让排序把它们压下去        |
| 全程模式里混进 2 小时速通 | 体量估算缺失 | 给短系列补 `total_minutes`，或确认 `episodes` 是否填成了 1                              |

## 参考

- `references/platforms.md` — B站 检索语法、合集与分P识别、免费/完结/存活判定、广告特征
- `references/scoring.md` — 四维打分、五道门禁、阈值、`llm_score` 锚点、合集优先的裁决规则
- `assets/candidates.example.json` — candidates.json 标准样例（含一条故意失效的链接与一条含网盘提取码的简介）
