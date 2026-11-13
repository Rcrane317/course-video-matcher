#!/usr/bin/env python3
"""align.py -- 在 B站 范围内做过滤、逐讲对齐打分与多候选排序。

过滤口径：
  1. 平台：只保留 bilibili.com / b23.tv 链接
  2. 广告：标题/UP主/简介命中卖课引流关键词的，整条丢弃
  3. 付费：series.free 明确为 false 的丢弃
  4. 未完结：series.status == "updating" 的丢弃
候选集 candidates.json 由 agent 检索后填写（见 assets/candidates.example.json）。
打分只做确定性计算，语义分由 agent 的 llm_score 承担。

用法：
    python align.py --materials work/materials.json --candidates work/candidates.json \
                    --out work/alignment.json
    python align.py --validate work/candidates.json --materials work/materials.json
"""

import argparse
import json
import re
import sys

# ---------------------------------------------------------------- 策略

PLATFORM = "bilibili"
PLATFORM_DOMAINS = ("bilibili.com", "b23.tv")

# 卖课/引流关键词，分两档：
#   STRONG -- 出现在标题/UP主，或出现在简介里，都算引流，直接丢
#   WEAK   -- 只在标题里出现才算（标题写「网盘」「资料包」基本是卖课）；
#             只在简介里出现则放行，因为大量正经免费课把课件放网盘，属于正常行为
AD_STRONG = [
    "扫码", "私信", "加微信", "加v", "vx", "微信", "qq群", "扣扣",
    "领取", "获取", "报名", "咨询", "一对一", "1对1", "保过", "包过",
    "押题", "内部资料", "辅导班", "培训班", "滴滴我", "评论区", "简介",
    "购买", "拼课", "代看", "代刷",
]
AD_WEAK = ["资料包", "网盘", "提取码"]
AD_KEYWORDS = AD_STRONG + AD_WEAK

CN_STOP = re.compile(r"[第章节讲次课部分篇]")
NOISE = re.compile(r"(课件|讲义|笔记|pptx|ppt|pdf|副本|final|v\d+|ok|new|改|终版)", re.I)
OFFICIAL_HINTS = ("大学", "学院", "教育", "官方", "课程组", "教务处", "学堂", "慕课", "研究院")


# ---------------------------------------------------------------- 相似度

def norm(s):
    s = (s or "").lower()
    s = NOISE.sub("", s)
    s = CN_STOP.sub("", s)
    return re.sub(r"[^\u4e00-\u9fa5a-z0-9]+", "", s)


def bigrams(s):
    s = norm(s)
    if not s:
        return set()
    return {s} if len(s) == 1 else {s[i:i + 2] for i in range(len(s) - 1)}


def jaccard(a, b):
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return inter / (len(A) + len(B) - inter)


def coverage_ratio(terms, haystack):
    terms = [norm(t) for t in terms if norm(t)]
    if not terms:
        return 0.0
    hay = norm(haystack)
    return sum(1 for t in terms if t and t in hay) / len(terms)


# ---------------------------------------------------------------- 过滤

def is_bilibili(url):
    u = str(url or "").lower()
    return u.startswith("http") and any(d in u for d in PLATFORM_DOMAINS)


def ad_hit(series, pick, keywords):
    """返回 (命中的词, 是否致命)。

    标题/UP主/分P名：任一档命中都致命（标题是门面，写这些就是在卖课）。
    简介正文：只有 STRONG 致命；WEAK（网盘/资料包/提取码）只作提示——
    很多正经免费课把课件放网盘，一律枪毙会误伤。
    刻意不查 note：note 里常有「简介没写章节」这类说明，查了会自己咬自己。
    """
    if keywords:
        strong, weak = set(keywords), set()
    else:
        strong, weak = set(AD_STRONG), set(AD_WEAK)

    head = " ".join(str(x) for x in (
        series.get("title"), series.get("uploader"),
        pick.get("episode"), pick.get("title"),
    ) if x).lower()
    for kw in list(strong) + list(weak):
        if kw.lower() in head:
            return kw, True

    desc = str(series.get("desc") or "").lower()
    for kw in strong:
        if kw.lower() in desc:
            return kw, True
    for kw in weak:
        if kw.lower() in desc:
            return kw, False
    return None, False


def gate(series, pick, keywords):
    """返回 (是否收纳, 门禁备注, 丢弃码)。"""
    if not is_bilibili(pick.get("url")) and not is_bilibili(series.get("url")):
        return False, "非B站链接", "other_platform"
    kw, fatal = ad_hit(series, pick, keywords)
    if kw and fatal:
        return False, f"命中广告词「{kw}」", "ad"
    soft = f"简介提到「{kw}」，可能是课件网盘，请自行判断" if kw else ""
    if series.get("free") is False:
        return False, "付费/需购买", "paid"
    status = (series.get("status") or "unknown").lower()
    if status == "updating":
        return False, "未更新完", "updating"
    notes = [soft] if soft else []
    if series.get("free") is None:
        notes.append("未确认免费")
    if status == "unknown":
        notes.append("未确认完结")
    return True, "；".join(notes), ""


DEAD_STATUS = {
    "dead": ("已删除或不可见", "dead"),
    "part_missing": ("分P不存在", "dead"),
    "paid": ("实际为付费稿件", "paid"),
    "restricted": ("充电专属，未充电看不了", "paid"),
    "mismatch": ("站内标题对不上，疑似错链接", "mismatch"),
}


def check_alive(url, probe, allow_unverified=False):
    """用 probe.json 判定这条链接此刻是否还能看。

    返回 (是否保留, 备注, 丢弃码, 核实信息 dict)
    """
    if not probe:
        return True, "", "", {}
    item = (probe.get("items") or {}).get(url)
    if not item:
        if allow_unverified:
            return True, "在播状态未核验", "", {"verified": False}
        return False, "未做在播核验", "unverified", {}

    st = item.get("status")
    if st == "alive":
        return True, "", "", {
            "verified": True,
            "verified_at": item.get("checked_at", ""),
            "real_title": item.get("title", ""),
            "real_owner": item.get("owner", ""),
            "page_title": item.get("page_title", ""),
            "page_count": item.get("page_count"),
            "real_duration": item.get("duration_min"),
            "pubdate": item.get("pubdate", ""),
            "title_match": item.get("title_match"),
        }
    if st in ("blocked", "error"):
        if allow_unverified or not probe.get("api_ok", True):
            return True, "在播状态未核验（接口受限）", "", {"verified": False}
        return False, "核验接口受限，无法确认可看", "unverified", {}
    note, code = DEAD_STATUS.get(st, (item.get("reason") or "不可用", "dead"))
    return False, note, code, {}


# ---------------------------------------------------------------- 打分

def score_pick(pick, match, series, deck):
    label = match.get("lecture_label") or deck["stem"]
    topics = match.get("topics") or []
    cand_text = " ".join(str(x) for x in (
        series.get("title"), series.get("uploader"),
        pick.get("episode"), pick.get("title"),
    ) if x)

    lex = jaccard(label, cand_text)
    topic_cov = coverage_ratio(topics, cand_text)
    base = 0.60 * lex + 0.25 * topic_cov

    adjust, reasons = 0.0, []
    if series.get("official") or any(h in str(series.get("uploader", "")) for h in OFFICIAL_HINTS):
        adjust += 0.06
        reasons.append("官方/高校/教育机构来源")
    dur = pick.get("duration_min")
    if isinstance(dur, (int, float)):
        if 4 <= dur <= 180:
            adjust += 0.02
        else:
            adjust -= 0.05
            reasons.append(f"时长异常 {dur} 分钟")
    if pick.get("evidence") == "page":
        adjust += 0.04
        reasons.append("已打开页面核实")
    else:
        reasons.append("仅搜索摘要，需核验")

    auto = max(0.0, min(1.0, base + adjust)) * 100
    llm = pick.get("llm_score")
    final = float(llm) if isinstance(llm, (int, float)) else auto
    return {
        "final": round(final, 1),
        "auto": round(auto, 1),
        "lex": round(lex, 3),
        "topic_cov": round(topic_cov, 3),
        "disagreement": isinstance(llm, (int, float)) and abs(float(llm) - auto) > 35,
        "reasons": reasons,
    }


def tier(score):
    if score >= 75:
        return "high", "高置信"
    if score >= 55:
        return "check", "待核验"
    if score >= 35:
        return "weak", "弱匹配"
    return "reject", "不推荐"


# ---------------------------------------------------------------- 校验

def validate(cand, materials):
    issues, warns = [], []
    course_ids = {c["id"] for c in materials["courses"]}
    deck_keys = set()
    for c in materials["courses"]:
        for d in c["decks"]:
            deck_keys.add((c["id"], d["rel"]))
            deck_keys.add((c["id"], d["name"]))

    seen = set()
    for course in cand.get("courses", []):
        cid = course.get("course_id")
        if cid not in course_ids:
            issues.append(f"未知 course_id：{cid}")
            continue
        sids = {}
        for s in course.get("series", []):
            sid = s.get("id")
            if not sid:
                issues.append(f"[{cid}] series 缺 id")
                continue
            sids[sid] = s
            if not is_bilibili(s.get("url")):
                issues.append(f"[{cid}] series {sid} 不是 B站链接：{s.get('url')}")
            if s.get("kind") not in ("collection", "snippet"):
                warns.append(f"[{cid}] series {sid} 的 kind 建议填 collection 或 snippet")
            if s.get("status") not in ("complete", "updating", "unknown"):
                warns.append(f"[{cid}] series {sid} 的 status 建议填 complete/updating/unknown")
            if "free" not in s:
                warns.append(f"[{cid}] series {sid} 未声明 free，将按「未确认免费」处理")

        for m in course.get("matches", []):
            key = (cid, m.get("deck_rel") or m.get("deck_name"))
            if key not in deck_keys:
                issues.append(f"[{cid}] 对不上的讲义：{key[1]}")
                continue
            if key in seen:
                issues.append(f"[{cid}] 讲义重复出现：{key[1]}")
            seen.add(key)
            for p in m.get("picks") or []:
                sid = p.get("series_id")
                if sid and sid not in sids:
                    issues.append(f"[{cid}] pick 引用了未声明的 series_id：{sid}")
                if not is_bilibili(p.get("url")):
                    issues.append(f"[{cid}] pick 不是 B站链接：{str(p.get('url'))[:60]}")
                if p.get("llm_score") is not None and not (0 <= p["llm_score"] <= 100):
                    issues.append(f"[{cid}] llm_score 越界：{p['llm_score']}")
    return issues, warns, len(seen)


# ---------------------------------------------------------------- 主流程

def align(materials, cand, keywords, probe=None, allow_unverified=False):
    by_id = {c["id"]: c for c in materials["courses"]}
    dropped = {"ad": 0, "paid": 0, "updating": 0, "other_platform": 0, "low_score": 0,
               "dead": 0, "mismatch": 0, "unverified": 0}
    out_courses = []

    for cc in cand.get("courses", []):
        mc = by_id.get(cc["course_id"])
        if not mc:
            continue
        series_map = {s["id"]: s for s in cc.get("series", []) if s.get("id")}
        match_map = {}
        for m in cc.get("matches", []):
            match_map[m.get("deck_rel") or m.get("deck_name")] = m

        decks_out = []
        for deck in mc["decks"]:
            m = match_map.get(deck["rel"]) or match_map.get(deck["name"]) or {}
            options = []
            deck_dropped = {}
            for p in m.get("picks") or []:
                s = series_map.get(p.get("series_id"), {})
                ok, why, code = gate(s, p, keywords)
                if not ok:
                    dropped[code] = dropped.get(code, 0) + 1
                    deck_dropped[code] = deck_dropped.get(code, 0) + 1
                    continue
                alive, alive_note, alive_code, alive_info = check_alive(
                    p.get("url"), probe, allow_unverified)
                if not alive:
                    dropped[alive_code] = dropped.get(alive_code, 0) + 1
                    deck_dropped[alive_code] = deck_dropped.get(alive_code, 0) + 1
                    continue
                # 站内真实时长优先，用来纠正手填的体量
                probed_dur = alive_info.get("real_duration")
                if probed_dur and not p.get("duration_min"):
                    p = {**p, "duration_min": probed_dur}
                sc = score_pick(p, m, s, deck)
                t, label = tier(sc["final"])
                if t == "reject":
                    dropped["low_score"] += 1
                    deck_dropped["low_score"] = deck_dropped.get("low_score", 0) + 1
                    continue
                options.append({
                    "series_id": p.get("series_id"),
                    "title": s.get("title") or p.get("title") or "",
                    "uploader": s.get("uploader") or "",
                    "kind": s.get("kind") or "snippet",
                    "url": p.get("url"),
                    "episode": p.get("episode") or "",
                    "duration_min": p.get("duration_min"),
                    "episodes": s.get("episodes"),
                    "official": bool(s.get("official")),
                    "free": s.get("free"),
                    "series_status": s.get("status") or "unknown",
                    "evidence": p.get("evidence"),
                    "verified": bool(alive_info.get("verified")),
                    "alive": alive_info,
                    "score": sc["final"],
                    "auto_score": sc["auto"],
                    "llm_score": p.get("llm_score"),
                    "tier": t,
                    "tier_label": label,
                    "disagreement": sc["disagreement"],
                    "gate_note": "；".join(x for x in (why, alive_note) if x),
                    "reasons": sc["reasons"] + ([p["note"]] if p.get("note") else []),
                })

            options.sort(key=lambda x: -x["score"])
            for i, o in enumerate(options, 1):
                o["rank"] = i
            options = options[:10]

            cols = [o for o in options if o["kind"] == "collection"]
            snips = [o for o in options if o["kind"] != "collection"]
            cols_ok = [o for o in cols if o["tier"] != "weak"]
            snips_ok = [o for o in snips if o["tier"] != "weak"]
            if cols_ok:
                primary, status, stage = cols_ok[0], "collection", "完整合集"
            elif snips_ok:
                primary, status, stage = snips_ok[0], "snippet", "专题片段"
            elif options:
                primary, status, stage = options[0], "weak", "仅弱匹配"
            elif deck.get("dup_of"):
                primary, status, stage = None, "dup", "重复文件"
            else:
                primary, status, stage = None, "not_found", "未找到"

            status_label = {
                "collection": "合集可用",
                "snippet": "仅专题片段",
                "weak": "仅弱匹配",
                "dup": "重复文件",
                "not_found": "未找到",
            }[status]

            decks_out.append({
                "deck_rel": deck["rel"],
                "deck_name": deck["name"],
                "lecture_label": m.get("lecture_label") or deck["stem"],
                "order": {"chapter": deck["chapter"], "section": deck["section"],
                          "lecture": deck["lecture"]},
                "dup_of": deck["dup_of"],
                "topics": m.get("topics") or [],
                "status": status,
                "status_label": status_label,
                "stage": stage,
                "option_count": len(options),
                "dropped": deck_dropped,
                "options": options,
            })

        eff = [d for d in decks_out if d["status"] != "dup"]
        covered = [d for d in eff if d["status"] in ("collection", "snippet")]
        out_courses.append({
            "course_id": cc["course_id"],
            "course_name": cc.get("course_name") or mc["name_guess"],
            "identity": cc.get("identity", {}),
            "series": [s for s in series_map.values() if s.get("kind") == "collection"],
            "decks": decks_out,
            "coverage": {
                "total": len(decks_out),
                "dup": len(decks_out) - len(eff),
                "collection": sum(1 for d in eff if d["status"] == "collection"),
                "snippet": sum(1 for d in eff if d["status"] == "snippet"),
                "weak": sum(1 for d in eff if d["status"] == "weak"),
                "not_found": sum(1 for d in eff if d["status"] == "not_found"),
                "needs_review": sum(1 for d in eff
                                    if d["options"] and d["options"][0]["tier"] == "check"),
                "coverage_pct": round(len(covered) / len(eff) * 100, 1) if eff else 0.0,
            },
        })

    tot = sum(c["coverage"]["total"] - c["coverage"]["dup"] for c in out_courses)
    cov = sum(c["coverage"]["collection"] + c["coverage"]["snippet"] for c in out_courses)
    return {
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "policy": {
            "platform": PLATFORM,
            "free_only": True,
            "complete_only": True,
            "collection_first": True,
            "alive_check": bool(probe),
            "allow_unverified": bool(allow_unverified),
            "ad_keywords": list(keywords or AD_KEYWORDS),
        },
        "probe": ({"generated_at": probe.get("generated_at"),
                   "api_ok": probe.get("api_ok"),
                   "stats": probe.get("stats", {})} if probe else None),
        "filters": dropped,
        "summary": {
            "course_count": len(out_courses),
            "deck_count": tot,
            "covered": cov,
            "coverage_pct": round(cov / tot * 100, 1) if tot else 0.0,
            "collection_covered": sum(c["coverage"]["collection"] for c in out_courses),
            "snippet_only": sum(c["coverage"]["snippet"] for c in out_courses),
            "weak_only": sum(c["coverage"]["weak"] for c in out_courses),
            "not_found": sum(c["coverage"]["not_found"] for c in out_courses),
            "needs_review": sum(c["coverage"]["needs_review"] for c in out_courses),
            "option_total": sum(len(d["options"]) for c in out_courses for d in c["decks"]),
            "verified": sum(1 for c in out_courses for d in c["decks"]
                            for o in d["options"] if o.get("verified")),
            "unverified": sum(1 for c in out_courses for d in c["decks"]
                              for o in d["options"] if not o.get("verified")),
        },
        "courses": out_courses,
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--materials")
    ap.add_argument("--candidates")
    ap.add_argument("--out")
    ap.add_argument("--validate", metavar="CANDIDATES_JSON")
    ap.add_argument("--ad-keywords", help="逗号分隔，覆盖内置广告词表")
    ap.add_argument("--probe", help="probe.json 路径；给了就按「此刻是否还能看」过滤")
    ap.add_argument("--allow-unverified", action="store_true",
                    help="核验接口受限时仍保留（默认丢弃）")
    args = ap.parse_args()

    keywords = ([k.strip() for k in args.ad_keywords.split(",") if k.strip()]
                if args.ad_keywords else None)

    if args.validate:
        cand = json.loads(open(args.validate, encoding="utf-8").read())
        mat = json.loads(open(args.materials, encoding="utf-8").read())
        issues, warns, n = validate(cand, mat)
        print(f"校验完成：{n} 份讲义，口径 = 仅 B站 + 免费 + 完结 + 无广告词")
        for w in warns:
            print(f"  [提示] {w}")
        if issues:
            print(f"\n发现 {len(issues)} 个问题，修好再跑：")
            for i in issues:
                print(f"  [错误] {i}")
            sys.exit(1)
        print("契约校验通过。")
        return

    if not (args.materials and args.candidates and args.out):
        ap.error("需要 --materials --candidates --out（或 --validate）")

    mat = json.loads(open(args.materials, encoding="utf-8").read())
    cand = json.loads(open(args.candidates, encoding="utf-8").read())
    probe = json.loads(open(args.probe, encoding="utf-8").read()) if args.probe else None
    if probe and not probe.get("api_ok", True):
        print("[警告] probe.json 显示过半探测请求失败，本次「在播」结论不可信；"
              "相关条目将标为未核验。", file=sys.stderr)

    issues, warns, _ = validate(cand, mat)
    for w in warns:
        print(f"[提示] {w}", file=sys.stderr)
    if issues:
        print(f"[警告] 候选集有 {len(issues)} 处问题，仍继续，请回头修：", file=sys.stderr)
        for i in issues[:10]:
            print(f"  - {i}", file=sys.stderr)

    result = align(mat, cand, keywords, probe, args.allow_unverified)
    with open(args.out, "w", encoding="utf-8") as f:
        json.dump(result, f, ensure_ascii=False, indent=2)

    s, fd = result["summary"], result["filters"]
    print(f"对齐完成：{s['course_count']} 门 / {s['deck_count']} 份讲义 / 覆盖 {s['coverage_pct']}%"
          f"（合集 {s['collection_covered']}，仅片段 {s['snippet_only']}，缺 {s['not_found']}）")
    print(f"过滤丢弃：广告 {fd.get('ad', 0)} · 付费 {fd.get('paid', 0)} · "
          f"未完结 {fd.get('updating', 0)} · 非B站 {fd.get('other_platform', 0)} · "
          f"低分 {fd.get('low_score', 0)}")
    if probe:
        print(f"在播核验：已删除/不可见 {fd.get('dead', 0)} · 标题不符 {fd.get('mismatch', 0)} · "
              f"无法核验 {fd.get('unverified', 0)}")
        print(f"          保留 {s['verified']} 条已核实在播"
              + (f"，{s['unverified']} 条未核验" if s['unverified'] else ""))
    else:
        print("提示：未提供 --probe，本次没有做「是否已被删除」的核验。", file=sys.stderr)
    print(f"候选总数：{s['option_total']} 条（按匹配度降序写入 HTML）")
    for c in result["courses"]:
        cv = c["coverage"]
        print(f"  [{c['course_id']}] {c['course_name']}: 合集 {cv['collection']} / "
              f"仅片段 {cv['snippet']} / 缺 {cv['not_found']}  (覆盖 {cv['coverage_pct']}%)")
    print(f"[输出] {args.out}")


if __name__ == "__main__":
    main()
