#!/usr/bin/env python3
"""write_html.py -- 把 alignment.json 渲染成一个自带交互的单文件 HTML 对照表。

产物特点：
  - 每条推荐都是可点开的 B站链接（target=_blank）
  - 同一讲按匹配度从高到低列出全部候选，用户自己挑
  - 合集优先：完整合集排在最前，专题片段单独标注
  - 顶部可筛选（课程 / 状态 / 只看合集 / 关键词），纯前端，无外部依赖

用法：
    python write_html.py work/alignment.json -o 网课对照表.html
"""

import argparse
import html
import json
from pathlib import Path

E = lambda s: html.escape(str(s if s is not None else ""), quote=True)

CSS = r"""
*{box-sizing:border-box}
:root{
  --bg:#f5f6f8; --card:#ffffff; --ink:#1a1d21; --ink2:#5b6470; --ink3:#8a929c;
  --line:#e6e8eb; --line2:#eef0f2;
  --blue:#1f4e79; --blue2:#2f6ea5;
  --green:#12805c; --green-bg:#e9f6f1;
  --amber:#a86400; --amber-bg:#fdf3e0;
  --gray:#6b7280; --gray-bg:#f2f3f5;
  --red:#b42318; --red-bg:#fdeceb;
}
html,body{margin:0;padding:0;background:var(--bg);color:var(--ink);
  font-family:-apple-system,BlinkMacSystemFont,"Segoe UI","PingFang SC","Hiragino Sans GB","Microsoft YaHei",sans-serif;
  font-size:14px;line-height:1.6;-webkit-font-smoothing:antialiased}
a{color:var(--blue2);text-decoration:none}
a:hover{text-decoration:underline}
.wrap{max-width:1180px;margin:0 auto;padding:0 20px 80px}

/* ---------- 头部 ---------- */
header{background:linear-gradient(135deg,#1f3b5c 0%,#2f5e8f 100%);color:#fff;padding:34px 0 26px;margin-bottom:0}
header .wrap{padding-bottom:0}
h1{margin:0 0 6px;font-size:25px;font-weight:650;letter-spacing:.3px}
.sub{margin:0;color:#c8d8e8;font-size:13px}
.stats{display:flex;flex-wrap:wrap;gap:8px;margin-top:16px}
.stat{background:rgba(255,255,255,.13);border:1px solid rgba(255,255,255,.2);
  border-radius:8px;padding:7px 12px;font-size:12.5px;color:#eaf2fa}
.stat b{font-size:15px;font-weight:650;color:#fff;margin-right:4px}

/* ---------- 工具条 ---------- */
.toolbar{position:sticky;top:0;z-index:20;background:rgba(245,246,248,.94);
  backdrop-filter:blur(8px);border-bottom:1px solid var(--line);padding:11px 0}
.toolbar .wrap{display:flex;flex-wrap:wrap;gap:9px;align-items:center;padding-bottom:0}
select,input[type=search]{font:inherit;font-size:13px;padding:6px 10px;border:1px solid #d5d9de;
  border-radius:7px;background:#fff;color:var(--ink);outline:none}
select:focus,input:focus{border-color:var(--blue2);box-shadow:0 0 0 3px rgba(47,110,165,.12)}
input[type=search]{min-width:220px;flex:1 1 220px;max-width:340px}
.chk{display:inline-flex;align-items:center;gap:6px;font-size:13px;color:var(--ink2);
  background:#fff;border:1px solid #d5d9de;border-radius:7px;padding:6px 11px;cursor:pointer;user-select:none}
.chk input{margin:0;accent-color:var(--blue2)}
.count{margin-left:auto;font-size:12.5px;color:var(--ink3)}

/* ---------- 图例 ---------- */
.legend{display:flex;flex-wrap:wrap;gap:14px;align-items:center;background:var(--card);
  border:1px solid var(--line);border-radius:10px;padding:12px 16px;margin:20px 0 6px;font-size:12.5px;color:var(--ink2)}
.legend b{color:var(--ink);font-weight:600}
.dot{display:inline-block;width:8px;height:8px;border-radius:2px;margin-right:5px;vertical-align:1px}

/* ---------- 课程 ---------- */
.course{background:var(--card);border:1px solid var(--line);border-radius:12px;
  margin:18px 0;overflow:hidden}
.chead{padding:20px 22px 16px;border-bottom:1px solid var(--line2);background:#fbfcfd}
.chead h2{margin:0;font-size:18px;font-weight:650;display:flex;align-items:center;gap:10px;flex-wrap:wrap}
.mode-badge{display:inline-block;font-size:12px;font-weight:600;letter-spacing:.4px;
  background:rgba(255,255,255,.18);border:1px solid rgba(255,255,255,.35);
  color:#fff;border-radius:20px;padding:3px 12px;vertical-align:3px;margin-left:10px}
.cid{font-size:11px;font-weight:500;color:var(--ink3);border:1px solid var(--line);
  border-radius:5px;padding:2px 7px;background:#fff}
.ident{margin-top:8px;display:flex;flex-wrap:wrap;gap:6px}
.ident span{font-size:12px;color:var(--ink2);background:var(--gray-bg);border-radius:5px;padding:2px 8px}
.barmini{display:flex;align-items:center;gap:10px;margin-top:12px;font-size:12px;color:var(--ink3)}
.bar{flex:1;max-width:320px;height:6px;background:#eceef1;border-radius:4px;overflow:hidden}
.bar>i{display:block;height:100%;background:linear-gradient(90deg,#2f6ea5,#3fa17c);border-radius:4px}

/* ---------- 讲义块 ---------- */
.deck{display:grid;grid-template-columns:210px 1fr;gap:0;border-bottom:1px solid var(--line2)}
.deck:last-child{border-bottom:none}
.deck:hover{background:#fcfdfe}
.dinfo{padding:16px 14px 16px 22px;border-right:1px solid var(--line2);background:#fcfdfe}
.dnum{font-size:11px;color:var(--ink3);letter-spacing:.5px;font-weight:600}
.dname{margin:2px 0 4px;font-size:14px;font-weight:600;line-height:1.45}
.dfile{margin:0;font-size:11.5px;color:var(--ink3);word-break:break-all}
.dtopics{margin:6px 0 0;font-size:11.5px;color:var(--ink2)}
.pill{display:inline-block;margin-top:8px;font-size:11px;font-weight:600;
  border-radius:5px;padding:2px 8px;white-space:nowrap}
.st-collection{color:var(--green);background:var(--green-bg)}
.st-snippet{color:var(--amber);background:var(--amber-bg)}
.st-weak{color:var(--gray);background:var(--gray-bg)}
.st-not_found{color:var(--red);background:var(--red-bg)}
.st-dup{color:var(--gray);background:var(--gray-bg)}

/* ---------- 候选列表 ---------- */
.opts{list-style:none;margin:0;padding:10px 18px 12px 16px}
.opt{display:grid;grid-template-columns:26px 54px 1fr auto;gap:11px;align-items:start;
  padding:11px 10px;border-radius:9px;border:1px solid transparent}
.opt+.opt{border-top:1px dashed #e9ebee;border-radius:0}
.opt:hover{background:#f7f9fb;border-color:var(--line2);border-radius:9px}
.rk{font-size:12px;font-weight:700;color:var(--ink3);text-align:center;padding-top:3px}
.sc{text-align:center;border-radius:7px;padding:4px 0 3px;font-variant-numeric:tabular-nums}
.sc b{display:block;font-size:15px;font-weight:700;line-height:1.15}
.sc i{font-size:10px;font-style:normal;opacity:.85}
.sc.high{background:var(--green-bg);color:var(--green)}
.sc.check{background:var(--amber-bg);color:var(--amber)}
.sc.weak{background:var(--gray-bg);color:var(--gray)}
.ttl{font-size:14px;font-weight:600;color:var(--blue);line-height:1.45}
.ttl:hover{color:var(--blue2)}
.sub2{margin-top:3px;display:flex;flex-wrap:wrap;gap:4px 12px;font-size:12px;color:var(--ink2)}
.tags{margin-top:6px;display:flex;flex-wrap:wrap;gap:5px}
.tag{font-size:11px;border-radius:4px;padding:1px 7px;background:var(--gray-bg);color:var(--ink2);
  border:1px solid transparent}
.tag.col{background:#e8f0f8;color:#1f4e79;font-weight:600}
.tag.ofc{background:#eaf4ff;color:#12558f}
.tag.warn{background:var(--amber-bg);color:var(--amber)}
.tag.bad{background:var(--red-bg);color:var(--red)}
.tag.ok{background:var(--green-bg);color:var(--green);font-weight:600}
.note{margin:6px 0 0;font-size:12px;color:var(--ink3);line-height:1.55}
.open{font-size:12.5px;font-weight:600;color:#fff;background:var(--blue2);border-radius:7px;
  padding:7px 13px;white-space:nowrap;align-self:center}
.open:hover{background:#2a6291;text-decoration:none}
.none{padding:18px 22px;font-size:13px;color:var(--ink3)}
.none.miss{color:#8a5a55;background:#fdf9f9;border-left:3px solid #e7c3be;margin:14px 18px;
  border-radius:0 8px 8px 0;padding:14px 16px}
.none.miss b{color:#a3463c;font-weight:600}
.empty{padding:22px;text-align:center;color:var(--ink3);font-size:13px}

/* ---------- 样例条 ---------- */
.samplebar{background:#fff4d6;color:#7a5a00;border-bottom:1px solid #f0dfa8;
  font-size:12.5px;padding:8px 20px;text-align:center;letter-spacing:.2px}

/* ---------- 页脚 ---------- */
footer{margin-top:34px;padding-top:18px;border-top:1px solid var(--line);font-size:12px;color:var(--ink3);line-height:1.8}
footer b{color:var(--ink2);font-weight:600}
.hidden{display:none !important}

@media (max-width:820px){
  .deck{grid-template-columns:1fr}
  .dinfo{border-right:none;border-bottom:1px solid var(--line2);padding:14px 18px}
  .opt{grid-template-columns:22px 46px 1fr;grid-template-areas:"rk sc body" "rk sc open"}
  .rk{grid-area:rk}.sc{grid-area:sc}
  .opt>div.body{grid-area:body}.open{grid-area:open;justify-self:start;margin-top:8px}
  .count{margin-left:0}
}
@media print{
  .toolbar,.open{display:none!important}
  body{background:#fff}
  .course{break-inside:avoid;box-shadow:none}
  header{background:#1f3b5c!important;-webkit-print-color-adjust:exact;print-color-adjust:exact}
}
"""

JS = r"""
(function(){
  var $=function(s){return document.querySelector(s)};
  var decks=Array.prototype.slice.call(document.querySelectorAll('.deck'));
  var courseSel=$('#fCourse'), statusSel=$('#fStatus'), kw=$('#fKw'), colOnly=$('#fCol'), cnt=$('#cnt');
  function apply(){
    var c=courseSel.value, st=statusSel.value, q=(kw.value||'').trim().toLowerCase();
    var onlyCol=colOnly.checked, shown=0;
    decks.forEach(function(d){
      var ok=(!c||d.dataset.course===c)&&(!st||d.dataset.status===st)&&
             (!onlyCol||d.dataset.hascol==='1')&&(!q||d.dataset.haystack.indexOf(q)>=0);
      d.classList.toggle('hidden',!ok);
      if(ok){shown++}
    });
    Array.prototype.forEach.call(document.querySelectorAll('.course'),function(sec){
      var vis=sec.querySelectorAll('.deck:not(.hidden)').length;
      sec.classList.toggle('hidden',vis===0);
    });
    cnt.textContent='显示 '+shown+' / '+decks.length+' 讲';
  }
  try{
    var p=new URLSearchParams(location.search);
    if(p.get('course')){courseSel.value=p.get('course')}
    if(p.get('status')){statusSel.value=p.get('status')}
    if(p.get('q')){kw.value=p.get('q')}
    if(p.get('col')==='1'){colOnly.checked=true}
  }catch(e){}
  [courseSel,statusSel,kw].forEach(function(el){el.addEventListener('input',apply)});
  colOnly.addEventListener('change',apply);
  apply();
})();
"""


def score_cls(tier):
    return {"high": "high", "check": "check", "weak": "weak"}.get(tier, "weak")


SC_SHORT = {"high": "高", "check": "待核", "weak": "弱"}


def order_text(order):
    bits = []
    if order.get("chapter"):
        bits.append(f"第{order['chapter']}章")
    if order.get("section"):
        s = order["section"]
        bits.append(f"{s // 100}.{s % 100}" if s >= 100 else f"第{s}节")
    if order.get("lecture"):
        bits.append(f"第{order['lecture']}讲")
    return " ".join(bits)


def option_html(o, deck_status):
    tags = []
    if o["kind"] == "collection":
        tags.append('<span class="tag col">完整合集</span>')
        if o.get("episodes"):
            tags.append(f'<span class="tag">共 {o["episodes"]} 集</span>')
        if o.get("total_hours"):
            tags.append(f'<span class="tag">整门 ≈{o["total_hours"]} 小时</span>')
        if o.get("series_status") == "complete":
            tags.append('<span class="tag">已完结</span>')
        elif o.get("series_status") == "unknown":
            tags.append('<span class="tag warn">完结未确认</span>')
    else:
        tags.append('<span class="tag">专题片段</span>')
    if o.get("free") is True:
        tags.append('<span class="tag">免费</span>')
    elif o.get("free") is None:
        tags.append('<span class="tag warn">免费未确认</span>')
    if o.get("official"):
        tags.append('<span class="tag ofc">官方/高校</span>')
    if o.get("verified"):
        raw = str((o.get("alive") or {}).get("verified_at") or "")
        at = raw[5:16].replace("T", " ") if len(raw) >= 16 else raw
        tags.append(f'<span class="tag ok">✓ 已核实在播{f" · {at}" if at else ""}</span>')
    elif o.get("alive") is not None:
        tags.append('<span class="tag warn">在播未核验</span>')
    if not o.get("verified"):
        if o.get("evidence") == "page":
            tags.append('<span class="tag">已看页面</span>')
        else:
            tags.append('<span class="tag warn">仅搜索摘要</span>')
    if o.get("gate_note"):
        tags.append(f'<span class="tag warn">{E(o["gate_note"])}</span>')

    sub = []
    al = o.get("alive") or {}
    pt = al.get("page_title") or ""
    if pt:
        sub.append(f'<span>站内 P{al.get("p", "")}：{E(pt[:32])}</span>')
    elif o.get("episode"):
        sub.append(f'<span>{E(o["episode"])}</span>')
    if o.get("duration_min"):
        sub.append(f'<span>{E(o["duration_min"])} 分钟</span>')
    if o.get("uploader"):
        sub.append(f'<span>UP：{E(o["uploader"])}</span>')

    note = "；".join(o.get("reasons") or [])
    url = o.get("url") or ""
    return f'''      <li class="opt">
        <span class="rk">{o.get("rank", "")}</span>
        <div class="sc {score_cls(o.get("tier"))}"><b>{int(o["score"])}</b><i>{SC_SHORT.get(o.get("tier"), "")}</i></div>
        <div class="body">
          <a class="ttl" href="{E(url)}" target="_blank" rel="noopener noreferrer">{E(o.get("title") or "（未命名）")}</a>
          <div class="sub2">{"".join(sub)}</div>
          <div class="tags">{"".join(tags)}</div>
          {f'<p class="note">{E(note)}</p>' if note else ""}
        </div>
        <a class="open" href="{E(url)}" target="_blank" rel="noopener noreferrer">打开 B站 ↗</a>
      </li>'''


def deck_html(d, course_id, idx, total):
    order = order_text(d["order"])
    topics = " · ".join(d.get("topics") or [])
    hay = " ".join([d["deck_name"], d["lecture_label"], topics,
                    " ".join(o.get("title", "") for o in d["options"])]).lower()
    has_col = "1" if any(o["kind"] == "collection" for o in d["options"]) else "0"

    if d["options"]:
        body = f'<ol class="opts">{"".join(option_html(o, d["status"]) for o in d["options"])}</ol>'
    else:
        why = ""
        names = {"dead": "已删除/不可见", "paid": "付费", "updating": "未更新完",
                 "ad": "广告卖课", "other_platform": "非B站", "low_score": "匹配度过低",
                 "mismatch": "链接与标题不符", "unverified": "无法核验在播"}
        dd = d.get("dropped") or {}
        if dd:
            bits = "、".join(f"{names.get(k, k)} {v} 条" for k, v in sorted(dd.items()))
            total = sum(dd.values())
            why = (f'<br>本来找到 {total} 条候选，因「{bits}」全部被排除'
                   f'{"（搜到的那几条已经没得看了）" if dd.get("dead") else ""}。')
        body = ('<div class="none miss"><b>这一讲没有符合条件、且此刻还能看的结果。</b>'
                f'{why}<br>'
                '口径是「B站 + 免费 + 已更新完毕 + 无广告 + 未删除」，五条都过才收录，所以这里宁缺勿滥。'
                '建议换课程简称或教材名重搜；也可以看报告里给的替代方案。</div>')

    dup = (f'<p class="note">与「{E(d["dup_of"])}」内容重复，可忽略。</p>'
           if d.get("dup_of") else "")

    return f'''    <article class="deck" data-course="{E(course_id)}" data-status="{E(d["status"])}" data-hascol="{has_col}" data-haystack="{E(hay)}">
      <div class="dinfo">
        <div class="dnum">{idx:02d} / {total:02d}</div>
        <h3 class="dname">{E(order) + "　" if order else ""}{E(d["lecture_label"])}</h3>
        <p class="dfile">{E(d["deck_name"])}</p>
        {f'<p class="dtopics">{E(topics)}</p>' if topics else ""}
        {dup}
        <span class="pill st-{E(d["status"])}">{E(d["status_label"])} · {len(d["options"])} 个候选</span>
      </div>
      <div class="body">{body}</div>
    </article>'''


def course_html(c):
    cv = c["coverage"]
    ident = "".join(f'<span>{E(k)}：{E(v)}</span>' for k, v in (c.get("identity") or {}).items() if v)
    eff = [d for d in c["decks"] if d["status"] != "dup"]
    rows = "".join(deck_html(d, c["course_id"], i, len(eff)) for i, d in enumerate(eff, 1))
    missing = [d for d in c["decks"] if d["status"] == "dup"]
    dupnote = ""
    if missing:
        dupnote = (f'<div class="none">另有 {len(missing)} 份重复课件已跳过：'
                   + "、".join(E(d["deck_name"]) for d in missing) + "</div>")
    return f'''  <section class="course">
    <div class="chead">
      <h2>{E(c["course_name"])}<span class="cid">{E(c["course_id"])}</span></h2>
      {f'<div class="ident">{ident}</div>' if ident else ""}
      <div class="barmini">
        <span>覆盖 {cv["coverage_pct"]}%</span>
        <span class="bar"><i style="width:{min(cv["coverage_pct"], 100)}%"></i></span>
        <span>合集 {cv["collection"]} · 仅片段 {cv.get("snippet", 0)} · 弱 {cv.get("weak", 0)} · 缺 {cv["not_found"]}</span>
      </div>
    </div>
    {rows}
    {dupnote}
  </section>'''


def build(alignment, title, sample=False):
    s, fd, pol = alignment["summary"], alignment["filters"], alignment["policy"]
    stats = [
        ("门课", s["course_count"]),
        ("份讲义", s["deck_count"]),
        ("候选视频", s["option_total"]),
        ("覆盖率", f'{s["coverage_pct"]}%'),
        ("含合集", s["collection_covered"]),
        ("仅片段", s["snippet_only"]),
        ("弱匹配", s.get("weak_only", 0)),
        ("缺失", s["not_found"]),
    ]
    if (alignment.get("policy") or {}).get("alive_check"):
        stats.append(("已核实在播", s.get("verified", 0)))
    stat_html = "".join(f'<div class="stat"><b>{v}</b>{k}</div>' for k, v in stats)

    course_opts = "".join(
        f'<option value="{E(c["course_id"])}">{E(c["course_name"])}</option>'
        for c in alignment["courses"])

    body = "".join(course_html(c) for c in alignment["courses"])

    filtered = (f'广告 {fd.get("ad", 0)} · 付费 {fd.get("paid", 0)} · '
                f'未完结 {fd.get("updating", 0)} · 非B站 {fd.get("other_platform", 0)} · '
                f'低分 {fd.get("low_score", 0)}')
    probe = alignment.get("probe") or {}
    alive_line = ""
    if (alignment.get("policy") or {}).get("alive_check"):
        alive_line = (
            f'<b>在播核验</b>：{E(str(probe.get("generated_at", "")[:16]).replace("T", " "))} '
            f'逐条请求 B站 稿件接口。已删除/不可见 {fd.get("dead", 0)} 条、'
            f'标题与站内不符 {fd.get("mismatch", 0)} 条、'
            f'无法核验 {fd.get("unverified", 0)} 条，均已剔除或标注；'
            f'表内 {s.get("verified", 0)} 条为核验时仍可观看。<br>')

    samplebar = ('<div class="samplebar">示例数据 · 链接指向真实 B站 视频，仅用于演示版式与交互（请勿当作选课建议）</div>'
                 if sample else "")
    mode_now = pol.get("mode", "full")
    read_hint = ("每一讲先看「完整合集」那一组——跟着同一个系列看到底，顺序和深度最接近课件；"
                 "没有合集的讲才用「专题片段」补单点。"
                 if mode_now == "full" else
                 "突击模式下优先看整门体量小的冲刺课（几小时讲完那种）；"
                 "同分时选总时长更短的，先过一遍框架，需要细节再回「全程」模式查。")
    alive_tag = "链接已逐条核验可播 · " if pol.get("alive_check") else ""
    return f'''<!DOCTYPE html>
<html lang="zh-CN">
<head>
<meta charset="utf-8">
<meta name="viewport" content="width=device-width,initial-scale=1">
<title>{E(title)}</title>
<style>{CSS}</style>
</head>
<body>
{samplebar}
<header>
  <div class="wrap">
    <h1>课件 ↔ 网课对照表<span class="mode-badge">{E(pol.get("mode_label", "全程网课"))}</span></h1>
    <p class="sub">检索口径：仅 B站 · 只看免费 · 只收已更新完毕 · 已剔除广告卖课 · {E(pol.get("mode_label", "全程网课"))}优先 · 按匹配度降序 · {alive_tag}生成于 {E(alignment.get("generated_at", "")[:16].replace("T", " "))}</p>
    <div class="stats">{stat_html}</div>
  </div>
</header>

<div class="toolbar">
  <div class="wrap">
    <select id="fCourse"><option value="">全部课程</option>{course_opts}</select>
    <select id="fStatus">
      <option value="">全部状态</option>
      <option value="collection">有可用的完整合集</option>
      <option value="snippet">仅专题片段</option>
      <option value="weak">仅弱匹配</option>
      <option value="not_found">未找到</option>
    </select>
    <label class="chk"><input type="checkbox" id="fCol">只看有合集的讲</label>
    <input type="search" id="fKw" placeholder="搜章节、知识点或视频标题…">
    <span class="count" id="cnt"></span>
  </div>
</div>

<div class="wrap">
  <div class="legend">
    <span><b>匹配度</b></span>
    <span><span class="dot" style="background:#12805c"></span>75+ 高置信，可直接看</span>
    <span><span class="dot" style="background:#a86400"></span>55–74 待核验，缺一条证据</span>
    <span><span class="dot" style="background:#6b7280"></span>35–54 弱匹配，只当补充</span>
    <span style="margin-left:auto">每讲按匹配度从高到低列出全部候选，自行挑选</span>
  </div>
{body}
  <footer>
    <b>怎么读这张表</b>：{read_hint}<br>
    <b>过滤了什么</b>：{E(filtered)}。广告词表：{E("、".join(pol.get("ad_keywords", [])[:12]))} 等。<br>
    {alive_line}
    <b>可信度</b>：「已核实页面」= 打开过播放列表确认了分P；「仅搜索摘要」= 只看到搜索结果标题，点开前请对一下章名。<br>
    <b>说明</b>：本表只提供公开平台的播放页链接，不下载、不转存任何视频；链接失效或课程下架属平台行为，与匹配结果无关。
  </footer>
</div>
<script>{JS}</script>
</body>
</html>'''


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("alignment")
    ap.add_argument("-o", "--out", required=True)
    ap.add_argument("--title", default="课件 ↔ 网课对照表")
    ap.add_argument("--sample", action="store_true", help="加一条「示例数据」提示条")
    args = ap.parse_args()

    data = json.loads(Path(args.alignment).read_text("utf-8"))
    if not data.get("courses"):
        raise SystemExit("alignment.json 里没有课程，先跑 align.py")

    out = Path(args.out)
    out.parent.mkdir(parents=True, exist_ok=True)
    out.write_text(build(data, args.title, sample=args.sample), "utf-8")
    s = data["summary"]
    print(f"[html] {out}")
    print(f"       {s['course_count']} 门课 · {s['deck_count']} 讲 · "
          f"{s['option_total']} 个候选 · 覆盖 {s['coverage_pct']}%")


if __name__ == "__main__":
    main()
