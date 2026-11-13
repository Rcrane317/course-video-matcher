#!/usr/bin/env python3
"""materials.py -- 课件压缩包解包 + 课程/讲义清点 + 标题抽取。

零第三方依赖：.pptx / .docx / .xlsx 直接解析 OOXML，.zip/.tar 用标准库。
.7z 需要 py7zr（缺失时自动尝试安装）；.rar 需要 7z.exe 或 unrar。

用法：
    python materials.py <输入路径> --out <工作目录>
    python materials.py <输入路径> --out <工作目录> --no-unpack
    python materials.py <输入路径> --out <工作目录> --max-files 600

输出：<工作目录>/materials.json
"""

import argparse
import hashlib
import json
import os
import re
import shutil
import subprocess
import sys
import tarfile
import tempfile
import zipfile
from pathlib import Path

ARCHIVE_EXTS = {".zip", ".7z", ".rar", ".tar", ".gz", ".tgz", ".bz2", ".xz"}
DECK_EXTS = {".pptx", ".ppt", ".pdf", ".docx", ".doc", ".key", ".xps"}
SKIP_DIRS = {"__MACOSX", ".git", ".DS_Store"}

CN_NUM = {"一": 1, "二": 2, "三": 3, "四": 4, "五": 5, "六": 6, "七": 7, "八": 8,
          "九": 9, "十": 10, "十一": 11, "十二": 12, "十三": 13, "十四": 14,
          "十五": 15, "十六": 16, "十七": 17, "十八": 18, "十九": 19, "二十": 20}


def log(msg):
    print(msg, flush=True)


# ---------------------------------------------------------------- 解包

def _fix_zip_name(info):
    """修正 Windows 下打包的中文文件名（cp437 误解码）。"""
    if info.flag_bits & 0x800:
        return info.filename
    try:
        return info.filename.encode("cp437").decode("gbk")
    except (UnicodeEncodeError, UnicodeDecodeError):
        try:
            return info.filename.encode("cp437").decode("utf-8")
        except (UnicodeEncodeError, UnicodeDecodeError):
            return info.filename


def _safe_join(dest, name):
    target = (dest / name).resolve()
    if not str(target).startswith(str(dest.resolve())):
        return None
    return target


def unpack_zip(archive, dest):
    n = 0
    with zipfile.ZipFile(archive) as zf:
        for info in zf.infolist():
            name = _fix_zip_name(info)
            if name.endswith("/"):
                (dest / name).mkdir(parents=True, exist_ok=True)
                continue
            target = _safe_join(dest, name)
            if target is None:
                continue
            target.parent.mkdir(parents=True, exist_ok=True)
            with zf.open(info) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            n += 1
    return n


def unpack_tar(archive, dest):
    n = 0
    with tarfile.open(archive) as tf:
        for member in tf.getmembers():
            if member.isdir():
                continue
            if member.name.startswith("/") or ".." in Path(member.name).parts:
                continue
            target = dest / member.name
            target.parent.mkdir(parents=True, exist_ok=True)
            with tf.extractfile(member) as src, open(target, "wb") as out:
                shutil.copyfileobj(src, out)
            n += 1
    return n


def _find_7z():
    for cand in (
        shutil.which("7z"), shutil.which("7za"), shutil.which("7zz"),
        r"C:\Program Files\7-Zip\7z.exe",
        r"C:\Program Files (x86)\7-Zip\7z.exe",
        "/Applications/Keka.app/Contents/MacOS/Keka",
    ):
        if cand and Path(cand).exists():
            return cand
    return None


def unpack_7z(archive, dest):
    try:
        import py7zr
    except ImportError:
        log("  [7z] 未安装 py7zr，尝试自动安装 ...")
        subprocess.run([sys.executable, "-m", "pip", "install", "-q", "py7zr"],
                       check=False)
        try:
            import py7zr
        except ImportError:
            py7zr = None
    if py7zr is not None:
        with py7zr.SevenZipFile(archive) as zf:
            zf.extractall(dest)
        return len(list(dest.rglob("*")))

    sevenzip = _find_7z()
    if sevenzip:
        subprocess.run([sevenzip, "x", "-y", f"-o{dest}", str(archive)],
                       check=True, stdout=subprocess.DEVNULL)
        return len(list(dest.rglob("*")))
    raise RuntimeError(
        "无法解压 .7z：py7zr 安装失败且未找到 7z.exe。\n"
        "  解决：pip install py7zr    或    安装 7-Zip 后重试。"
    )


def unpack_rar(archive, dest):
    sevenzip = _find_7z()
    if sevenzip:
        subprocess.run([sevenzip, "x", "-y", f"-o{dest}", str(archive)],
                       check=True, stdout=subprocess.DEVNULL)
        return len(list(dest.rglob("*")))
    unrar = None
    for cand in (shutil.which("unrar"), shutil.which("unar"),
                 r"C:\Program Files\WinRAR\UnRAR.exe",
                 r"C:\Program Files\WinRAR\WinRAR.exe"):
        if cand and Path(cand).exists():
            unrar = cand
            break
    if unrar:
        subprocess.run([unrar, "x", "-y", str(archive), str(dest) + os.sep],
                       check=True, stdout=subprocess.DEVNULL)
        return len(list(dest.rglob("*")))
    raise RuntimeError(
        "无法解压 .rar：本机既没有 7-Zip 也没有 WinRAR/UnRAR。\n"
        "  解决（任一）：\n"
        "   1) 安装 7-Zip（https://www.7-zip.org）后重试；\n"
        "   2) 用资源管理器打开压缩包，全部解压后把文件夹路径传给我；\n"
        "   3) 把 .rar 另存为 .zip 再来。"
    )


def unpack_all(input_path, workdir):
    """解压输入（可能是压缩包，也可能是多层嵌套目录），返回素材根目录。"""
    dest = workdir / "materials"
    dest.mkdir(parents=True, exist_ok=True)
    input_path = Path(input_path)
    if not input_path.is_absolute():
        input_path = input_path.resolve()

    if input_path.is_dir():
        log(f"[输入] 目录，直接扫描：{input_path}")
        return input_path

    ext = input_path.suffix.lower()
    if ext not in ARCHIVE_EXTS:
        raise RuntimeError(f"不认识的输入类型：{input_path.name}（支持 .zip/.7z/.rar/.tar.gz 或文件夹）")

    target = dest / input_path.stem
    target.mkdir(parents=True, exist_ok=True)
    log(f"[解包] {input_path.name} -> {target}")
    if ext == ".zip":
        n = unpack_zip(input_path, target)
    elif ext in {".tar", ".gz", ".tgz", ".bz2", ".xz"}:
        n = unpack_tar(input_path, target)
    elif ext == ".7z":
        n = unpack_7z(input_path, target)
    elif ext == ".rar":
        n = unpack_rar(input_path, target)
    else:
        raise RuntimeError(f"暂不支持：{ext}")
    log(f"  -> {n} 个条目")

    # 压缩包里常常还套一层同名目录，剥掉
    entries = [p for p in target.iterdir() if p.name not in SKIP_DIRS]
    if len(entries) == 1 and entries[0].is_dir():
        log(f"  -> 剥掉嵌套目录：{entries[0].name}")
        return entries[0]
    return target


# ---------------------------------------------------------------- 文件名解析

CHAPTER_PATTERNS = [
    r"第\s*([0-9]{1,2}|[一二三四五六七八九十]{1,3})\s*章",
    r"[Cc]h(?:apter)?\s*[_\-]?([0-9]{1,2})",
    r"(?:^|[^0-9])([0-9]{1,2})\s*[-_\.]\s*[0-9]{1,2}\s*[-_\.\s]",
]
SECTION_PATTERNS = [
    r"第\s*([0-9]{1,3}|[一二三四五六七八九十]{1,3})\s*节",
    r"([0-9]{1,2})\s*[-_\.]\s*([0-9]{1,2})(?![0-9])",
]
LECTURE_PATTERNS = [
    r"第\s*([0-9]{1,3}|[一二三四五六七八九十]{1,3})\s*讲",
    r"第\s*([0-9]{1,3}|[一二三四五六七八九十]{1,3})\s*次课",
    r"[Ll](?:ecture|ec)?\s*[_\-]?([0-9]{1,3})",
    r"(?:^|[^0-9])[Ll](\d{1,3})(?![0-9])",
]


def _num(tok):
    if tok.isdigit():
        return int(tok)
    return CN_NUM.get(tok, 0)


def parse_order(text):
    """从文件名抽 (chapter, section, lecture)，抽不到为 None。"""
    chapter = section = lecture = None
    for pat in CHAPTER_PATTERNS:
        m = re.search(pat, text)
        if m:
            chapter = _num(m.group(1))
            break
    for pat in SECTION_PATTERNS:
        m = re.search(pat, text)
        if m:
            section = _num(m.group(1)) * 100 + _num(m.group(2)) if m.lastindex and m.lastindex >= 2 else _num(m.group(1))
            break
    for pat in LECTURE_PATTERNS:
        m = re.search(pat, text)
        if m:
            lecture = _num(m.group(1))
            break
    if chapter is None and section is None and lecture is None:
        m = re.match(r"^\s*0*(\d{1,3})[\s\-_\.、]", text)
        if m:
            lecture = int(m.group(1))
    return chapter, section, lecture


def clean_stem(name):
    stem = Path(name).stem
    stem = re.sub(r"[\(（]\s*\d+\s*[\)）]", " ", stem)          # (1) 副本标记
    stem = re.sub(r"[_\-]{2,}", " ", stem)
    stem = re.sub(r"\s{2,}", " ", stem)
    return stem.strip(" _-.")


# ---------------------------------------------------------------- 标题抽取

def _xml_texts(xml_bytes):
    """从 OOXML 里按顺序取出所有 <a:t>/<w:t> 文本。"""
    import xml.etree.ElementTree as ET
    out = []
    try:
        root = ET.fromstring(xml_bytes)
    except ET.ParseError:
        return out
    for el in root.iter():
        tag = el.tag.rsplit("}", 1)[-1]
        if tag in ("t", "instrText") and el.text:
            out.append(el.text)
    return out


def pptx_titles(path, max_slides=6):
    """返回 [(slide_index, first_line, joined_text_head)]，按演示顺序。"""
    titles = []
    try:
        with zipfile.ZipFile(path) as zf:
            names = set(zf.namelist())
            order = []
            if "ppt/presentation.xml" in names and "ppt/_rels/presentation.xml.rels" in names:
                import xml.etree.ElementTree as ET
                rels = ET.fromstring(zf.read("ppt/_rels/presentation.xml.rels"))
                rid2target = {}
                for rel in rels:
                    rid2target[rel.get("Id")] = rel.get("Target")
                pres = ET.fromstring(zf.read("ppt/presentation.xml"))
                for el in pres.iter():
                    if el.tag.rsplit("}", 1)[-1] == "sldId":
                        rid = None
                        for k, v in el.attrib.items():
                            if k.endswith("}id"):
                                rid = v
                        tgt = rid2target.get(rid)
                        if tgt:
                            order.append("ppt/" + tgt.lstrip("/").replace("ppt/", ""))
            if not order:
                order = sorted([n for n in names if re.match(r"ppt/slides/slide\d+\.xml$", n)],
                               key=lambda s: int(re.search(r"(\d+)\.xml$", s).group(1)))
            for idx, name in enumerate(order[:max_slides], 1):
                if name not in names:
                    continue
                texts = [t.strip() for t in _xml_texts(zf.read(name)) if t.strip()]
                first = texts[0] if texts else ""
                titles.append((idx, first, " ".join(texts)[:300]))
    except (zipfile.BadZipFile, KeyError):
        pass
    return titles


def docx_text(path, limit=800):
    try:
        with zipfile.ZipFile(path) as zf:
            if "word/document.xml" not in zf.namelist():
                return ""
            return " ".join(_xml_texts(zf.read("word/document.xml")))[:limit]
    except zipfile.BadZipFile:
        return ""


def _pdf_cli():
    cand = shutil.which("workbuddy-pdf")
    if cand:
        return cand
    home = Path.home()
    for p in (home / ".workbuddy" / "external-packages" / "pdf-cli").glob("workbuddy-pdf*"):
        if p.is_file():
            return str(p)
    return None


def _pdf_extractor():
    """返回 ("workbuddy-pdf"|"pdftotext", cli路径) 或 None。通用环境优先 poppler 的 pdftotext。"""
    cli = _pdf_cli()
    if cli:
        return ("workbuddy-pdf", cli)
    pt = shutil.which("pdftotext")
    if pt:
        return ("pdftotext", pt)
    return None


def pdf_text(path, max_pages=8):
    """抽 PDF 文本（workbuddy-pdf 或 pdftotext）；都没有就返回空（退化为文件名推断）。"""
    ext_pair = _pdf_extractor()
    if not ext_pair:
        return ""
    kind, cli = ext_pair
    tmp = Path(tempfile.mkdtemp(prefix="cvm-pdf-"))
    out = tmp / "out.txt"
    try:
        if kind == "pdftotext":
            subprocess.run([cli, "-f", "1", "-l", str(max_pages),
                            str(path), str(out)],
                           check=True, stdout=subprocess.DEVNULL,
                           stderr=subprocess.DEVNULL, timeout=180)
        else:
            subprocess.run([cli, str(path), str(out), "--format", "txt"],
                           check=True, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                           timeout=180)
        raw = out.read_text("utf-8", errors="ignore")
    except (subprocess.SubprocessError, OSError):
        return ""
    finally:
        shutil.rmtree(tmp, ignore_errors=True)
    pages = raw.split("\f")
    if len(pages) < 2:
        pages = [raw]
    head = []
    for page in pages[:max_pages]:
        lines = [ln.strip() for ln in page.splitlines() if ln.strip()]
        head.append(lines[:2])
    return "\n".join(" ".join(p) for p in head if p)[:1200]


def extract_titles(path):
    ext = path.suffix.lower()
    result = {"method": "filename_only", "slide_titles": [], "text_head": ""}
    try:
        if ext == ".pptx":
            titles = pptx_titles(path)
            if titles:
                result["method"] = "pptx_xml"
                result["slide_titles"] = [t[1] for t in titles if t[1]]
                result["text_head"] = titles[0][2] if titles else ""
                result["slide_count"] = len(titles)
        elif ext == ".pdf":
            txt = pdf_text(path)
            if txt:
                result["method"] = "pdf_text"
                result["text_head"] = txt
                chunks = [c.strip() for c in txt.split("\n") if c.strip()]
                short = [c for c in chunks if 2 < len(c) < 40]
                result["slide_titles"] = (short or [c[:38] for c in chunks])[:5]
        elif ext == ".docx":
            txt = docx_text(path)
            if txt:
                result["method"] = "docx_xml"
                result["text_head"] = txt
    except Exception as exc:  # 单文件失败不能拖垮整批
        result["error"] = f"{type(exc).__name__}: {exc}"
    return result


# ---------------------------------------------------------------- 扫描

COURSE_HINT = re.compile(r"(课程|课件|讲义|资料|复习|期末|期中|作业|习题|答案|试卷|总结|笔记)")
TEACHER_HINT = re.compile(r"(教授|老师|讲师|教师|主讲)")
SCHOOL_HINT = re.compile(r"(大学|学院|学校|University|College)")


def scan_courses(root, max_files=600):
    root = Path(root)
    decks = []
    for p in sorted(root.rglob("*")):
        if not p.is_file():
            continue
        if any(part in SKIP_DIRS for part in p.parts):
            continue
        if p.suffix.lower() in DECK_EXTS and p.stat().st_size > 1024:
            decks.append(p)

    if len(decks) > max_files:
        log(f"[警告] 素材文件 {len(decks)} 个，超过上限 {max_files}，只取前 {max_files} 个。"
            f"需要全量请加 --max-files。")
        decks = decks[:max_files]

    # 按顶层目录分组当作不同课程
    groups = {}
    for p in decks:
        rel = p.relative_to(root)
        key = rel.parts[0] if len(rel.parts) > 1 else "_root_"
        groups.setdefault(key, []).append(p)

    if list(groups.keys()) == ["_root_"]:
        # 全部平铺：按文件名前缀再聚类（前 4 个字 / 首个分隔符之前）
        flat = groups.pop("_root_")
        sub = {}
        for p in flat:
            stem = clean_stem(p.name)
            key = re.split(r"[\s\-_、]+", stem)[0] or stem
            sub.setdefault(key, []).append(p)
        if len(sub) > 8:  # 前缀太碎，说明确实是单门课
            groups["_root_"] = flat
        else:
            groups.update(sub)

    courses = []
    for ci, (folder, files) in enumerate(sorted(groups.items()), 1):
        # 去重：同一内容只认一个「正本」，优先不带 (1)/副本 字样、名字更短的那个
        hashes = {p: hashlib.sha1(p.read_bytes()[:65536]).hexdigest()[:10] for p in files}
        canon = {}
        dup_of = {}
        for p in sorted(files, key=lambda x: (bool(re.search(r"[\(（]\d+[\)）]|副本|copy|副本", x.name)),
                                              len(x.name), x.name)):
            h = hashes[p]
            if h in canon:
                dup_of[p] = canon[h].name
            else:
                canon[h] = p

        items = []
        for p in sorted(files):
            chapter, section, lecture = parse_order(p.name)
            info = extract_titles(p)
            items.append({
                "file": str(p),
                "rel": str(p.relative_to(root)),
                "name": p.name,
                "stem": clean_stem(p.name),
                "size_kb": round(p.stat().st_size / 1024),
                "chapter": chapter,
                "section": section,
                "lecture": lecture,
                "dup_of": dup_of.get(p),
                "sha": hashes[p],
                **info,
            })
        # 排序：章 -> 节 -> 讲 -> 正本优先 -> 文件名
        items.sort(key=lambda d: (d["chapter"] or 999, d["section"] or 999,
                                  d["lecture"] or 999, bool(d["dup_of"]), d["stem"], d["name"]))
        courses.append({
            "id": f"c{ci:02d}",
            "folder": folder,
            "name_guess": folder if folder != "_root_" else _guess_course_name(items),
            "signals": _collect_signals(folder, items),
            "decks": items,
        })
    return courses, len(decks)


def _guess_course_name(items):
    from collections import Counter
    cnt = Counter()
    for it in items:
        for tok in re.split(r"[\s\-_、,，.。]+", it["stem"]):
            if 2 <= len(tok) <= 12 and not tok.isdigit() and not COURSE_HINT.search(tok):
                cnt[tok] += 1
    return cnt.most_common(1)[0][0] if cnt else "_root_"


def _collect_signals(folder, items):
    teachers, schools, textbooks = set(), set(), set()
    for it in items[:40]:
        head = f"{it['stem']} {it.get('text_head','')[:200]}"
        for m in re.finditer(r"([\u4e00-\u9fa5]{2,4})\s*(?:教授|老师|讲师|教师)", head):
            teachers.add(m.group(1))
        for m in re.finditer(r"([\u4e00-\u9fa5]{2,12}(?:大学|学院))", head):
            schools.add(m.group(1))
        for m in re.finditer(r"(《[^》]{2,30}》)", head):
            textbooks.add(m.group(1))
        for m in re.finditer(r"(第[一二三四五六七八九十0-9]{1,2}版)", head):
            textbooks.add(m.group(1))
    return {
        "teachers": sorted(teachers)[:5],
        "schools": sorted(schools)[:3],
        "textbook": sorted(textbooks)[:3],
        "folder_has_school": bool(SCHOOL_HINT.search(folder)),
    }


def main():
    ap = argparse.ArgumentParser()
    ap.add_argument("input")
    ap.add_argument("--out", required=True, help="工作目录（存放 materials/ 与 materials.json）")
    ap.add_argument("--no-unpack", action="store_true", help="输入已是解压后的目录")
    ap.add_argument("--max-files", type=int, default=600)
    args = ap.parse_args()

    workdir = Path(args.out).resolve()
    workdir.mkdir(parents=True, exist_ok=True)

    root = Path(args.input).resolve() if args.no_unpack else unpack_all(args.input, workdir)
    log(f"[扫描] {root}")
    courses, total = scan_courses(root, args.max_files)

    payload = {
        "input": str(Path(args.input).resolve()),
        "materials_root": str(root),
        "generated_at": __import__("datetime").datetime.now().isoformat(timespec="seconds"),
        "stats": {
            "course_count": len(courses),
            "deck_count": total,
            "dup_count": sum(1 for c in courses for d in c["decks"] if d["dup_of"]),
            "text_unavailable": sum(1 for c in courses for d in c["decks"]
                                    if d["method"] == "filename_only"),
        },
        "courses": courses,
    }
    out = workdir / "materials.json"
    out.write_text(json.dumps(payload, ensure_ascii=False, indent=2), "utf-8")

    print()
    print(f"课程 {payload['stats']['course_count']} 门 / 讲义 {total} 份 / "
          f"重复 {payload['stats']['dup_count']} / 无正文 {payload['stats']['text_unavailable']}")
    for c in courses:
        log(f"  [{c['id']}] {c['name_guess']}  ({len(c['decks'])} 份)"
            f"  教师={c['signals']['teachers'] or '-'}  教材={c['signals']['textbook'] or '-'}")
        for d in c["decks"][:3]:
            log(f"       - {d['name'][:52]}  [{d['method']}]")
        if len(c["decks"]) > 3:
            log(f"       ... 另 {len(c['decks']) - 3} 份")
    print(f"\n[输出] {out}")


if __name__ == "__main__":
    try:
        main()
    except RuntimeError as e:
        print(f"错误：{e}", file=sys.stderr)
        sys.exit(1)
