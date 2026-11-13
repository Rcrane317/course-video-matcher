#!/usr/bin/env python3
"""probe.py -- 逐条探测 B站 稿件是否还能看，并在当场校验链接真伪。

只调一个公开接口：`/x/web-interface/view?bvid=...`，不登录、不下载。
它同时能给出四类判定所需的信息：

  · 存活   code 0 = 在播；-404「啥都木有」= 已删除；62002/62004 = 不可见/审核中
  · 分P    返回 pages 列表，能验证 ?p=N 是否真的存在
  · 付费   rights.pay / arc_pay / ugc_pay / is_chargeable_season / is_upower_exclusive
  · 真伪   真实标题与 candidates.json 里声明的标题做比对，编造的 BV 会当场露馅

用法：
    python probe.py --candidates work/candidates.json --out work/probe.json
    python probe.py --candidates work/candidates.json --out work/probe.json --strict
    python probe.py --url "https://www.bilibili.com/video/BV1xx411c7mD?p=3"

退出码：全部可看返回 0；有被剔除的返回 0（正常流程）；接口整体不可用返回 2。
"""

import argparse
import json
import re
import sys
import time
import urllib.error
import urllib.request
from concurrent.futures import ThreadPoolExecutor
from datetime import datetime
from pathlib import Path

API = "https://api.bilibili.com/x/web-interface/view?bvid={bvid}"
UA = ("Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 "
      "(KHTML, like Gecko) Chrome/124.0.0.0 Safari/537.36")

BV_RE = re.compile(r"(BV[0-9A-Za-z]{10})")
P_RE = re.compile(r"[?&]p=(\d+)")

# 不可见类错误码：稿件被删、被设为私密、审核中、被屏蔽
GONE_CODES = {-404: "已删除", 62002: "稿件不可见（删除或私密）",
              62004: "审核中", 62005: "被屏蔽", -403: "无访问权限"}
RISK_CODES = {-412: "触发风控", -352: "风控校验失败", -799: "请求过于频繁"}


def now():
    return datetime.now().isoformat(timespec="seconds")


def norm(s):
    s = re.sub(r"[^\u4e00-\u9fa5a-z0-9]+", "", str(s or "").lower())
    return s


def bigrams(s):
    s = norm(s)
    if not s:
        return set()
    return {s} if len(s) == 1 else {s[i:i + 2] for i in range(len(s) - 1)}


def sim(a, b):
    A, B = bigrams(a), bigrams(b)
    if not A or not B:
        return 0.0
    inter = len(A & B)
    return inter / (len(A) + len(B) - inter)


def parse_url(url):
    m = BV_RE.search(str(url or ""))
    if not m:
        return None, None
    p = P_RE.search(str(url or ""))
    return m.group(1), int(p.group(1)) if p else 1


def fetch(bvid, timeout=10, retries=2):
    url = API.format(bvid=bvid)
    req = urllib.request.Request(url, headers={
        "User-Agent": UA,
        "Referer": f"https://www.bilibili.com/video/{bvid}",
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "zh-CN,zh;q=0.9",
    })
    last = None
    for attempt in range(retries + 1):
        try:
            with urllib.request.urlopen(req, timeout=timeout) as r:
                return json.loads(r.read().decode("utf-8", "ignore"))
        except urllib.error.HTTPError as e:
            return {"code": f"HTTP{e.code}", "message": f"HTTP {e.code}"}
        except Exception as e:  # 超时、DNS、连接重置
            last = e
            time.sleep(0.8 * (attempt + 1))
    return {"code": "NET", "message": f"{type(last).__name__}: {str(last)[:60]}"}


def judge(bvid, p, declared_title, payload, play_url):
    code = payload.get("code")
    item = {
        "bvid": bvid, "p": p, "url": play_url,
        "declared_title": declared_title or "",
        "checked_at": now(),
        "code": code,
        "message": payload.get("message") or "",
    }

    if isinstance(code, str) or code in RISK_CODES:
        item["status"] = "blocked"
        item["reason"] = RISK_CODES.get(code, payload.get("message") or "接口不可用")
        return item
    if code != 0:
        item["status"] = "dead"
        item["reason"] = GONE_CODES.get(code, payload.get("message") or f"code={code}")
        return item

    d = payload.get("data") or {}
    rights = d.get("rights") or {}
    pages = d.get("pages") or []
    item.update({
        "title": d.get("title") or "",
        "owner": (d.get("owner") or {}).get("name") or "",
        "page_count": len(pages) or d.get("videos") or 1,
        "duration_min": round((d.get("duration") or 0) / 60) or None,
        "pubdate": datetime.fromtimestamp(d["pubdate"]).strftime("%Y-%m-%d")
        if d.get("pubdate") else "",
        "pay": bool(rights.get("pay") or rights.get("arc_pay")
                   or rights.get("ugc_pay") or d.get("is_chargeable_season")),
        "upower": bool(d.get("is_upower_exclusive") or d.get("is_upower_preview")),
    })

    if pages:
        hit = [pg for pg in pages if int(pg.get("page") or 0) == int(p or 1)]
        if hit:
            item["page_title"] = hit[0].get("part") or ""
            item["duration_min"] = round((hit[0].get("duration") or 0) / 60) or item["duration_min"]
        else:
            item["status"] = "part_missing"
            item["reason"] = f"该稿只有 {len(pages)} 个分P，链接指向 P{p}"
            return item

    if item["upower"]:
        item["status"] = "restricted"
        item["reason"] = "充电专属/充电预览，未充电看不了"
        return item
    if item["pay"]:
        item["status"] = "paid"
        item["reason"] = "付费稿件（试看或需购买）"
        return item

    title_match = sim(declared_title, item["title"] + " " + item.get("page_title", ""))
    item["title_match"] = round(title_match, 3)
    if declared_title and title_match < 0.10:
        item["status"] = "mismatch"
        item["reason"] = f"站内标题与此处声明不符，疑似链接写错（实际：「{item['title'][:28]}」）"
        return item

    item["status"] = "alive"
    item["reason"] = "可正常观看"
    return item


def collect_jobs(cand):
    """从 candidates.json 拆出所有待探测的 (bvid, p, declared_title, url)。"""
    jobs = {}
    for course in cand.get("courses", []):
        series = {s.get("id"): s for s in course.get("series", []) if s.get("id")}
        for m in course.get("matches", []):
            for pick in m.get("picks") or []:
                s = series.get(pick.get("series_id"), {})
                url = pick.get("url")
                bvid, p = parse_url(url)
                if not bvid:
                    continue
                jobs[url] = (bvid, p, s.get("title") or pick.get("title") or "", url)
    return jobs


def probe_all(jobs, sleep=0.4, workers=4):
    results = {}

    def work(kv):
        url, (bvid, p, title, play_url) = kv
        payload = fetch(bvid)
        return url, judge(bvid, p, title, payload, play_url)

    keys = list(jobs.items())
    with ThreadPoolExecutor(max_workers=workers) as pool:
        for url, item in pool.map(work, keys):
            results[url] = item
            time.sleep(sleep / max(1, workers))
    return results


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("--candidates")
    ap.add_argument("--out")
    ap.add_argument("--url", help="只探测这一条链接")
    ap.add_argument("--sleep", type=float, default=0.4, help="每条之间的间隔秒数")
    ap.add_argument("--workers", type=int, default=4)
    ap.add_argument("--timeout", type=int, default=10)
    args = ap.parse_args()

    if args.url:
        bvid, p = parse_url(args.url)
        if not bvid:
            raise SystemExit("链接里找不到 BV 号")
        item = judge(bvid, p, "", fetch(bvid, args.timeout), args.url)
        print(json.dumps(item, ensure_ascii=False, indent=2))
        return

    if not (args.candidates and args.out):
        ap.error("需要 --candidates 与 --out（或用 --url 单测）")

    cand = json.loads(Path(args.candidates).read_text("utf-8"))
    jobs = collect_jobs(cand)
    if not jobs:
        raise SystemExit("candidates.json 里没有可探测的 B站 链接")

    print(f"[探测] {len(jobs)} 条链接，并发 {args.workers} ...")
    items = probe_all(jobs, args.sleep, args.workers)

    stats = {}
    for it in items.values():
        stats[it["status"]] = stats.get(it["status"], 0) + 1
    blocked = stats.get("blocked", 0) + stats.get("error", 0)
    api_ok = blocked < len(items) * 0.5

    payload = {
        "generated_at": now(),
        "api": API,
        "api_ok": api_ok,
        "stats": stats,
        "items": items,
    }
    Path(args.out).write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    label = {"alive": "可看", "dead": "已删除/不可见", "part_missing": "分P不存在",
             "paid": "付费", "restricted": "充电专属", "mismatch": "链接与标题不符",
             "blocked": "接口被风控", "error": "网络失败"}
    print("\n探测结果：" + " · ".join(f"{label.get(k, k)} {v}" for k, v in sorted(stats.items())))
    for it in items.values():
        if it["status"] != "alive":
            print(f"  ✗ [{label.get(it['status'], it['status'])}] {it['url'][:62]}")
            print(f"      {it.get('reason', '')}")
    print(f"\n[输出] {args.out}")
    if not api_ok:
        print("警告：过半请求被风控/失败，本次探测不可信，应重跑或降级为人工核验。", file=sys.stderr)
        sys.exit(2)


if __name__ == "__main__":
    main()
