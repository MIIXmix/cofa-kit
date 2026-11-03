#!/usr/bin/env python3
"""제출 전 점검. 출력에는 파일:줄과 규칙 이름만 쓰고 비밀값, 개인정보 값은 쓰지 않는다."""
import argparse
import ast
import csv
import io
import os
import re
import subprocess
import sys
from itertools import islice

DEFAULT_REQUIRE = "README.md,NOTES.md,REQUIREMENTS.md,PLAN.md,PROGRESS.md,COLLAB_LOG.md"
SKIP_DIRS = {".git", "node_modules", ".venv", "venv", "__pycache__", "parked", "work", ".agents", ".codex"}
NOTES_KEYS = ["판단과 근거", "결정 카드", "검증 결과", "남은 한계", "데이터 처리"]
CONF_EXT = {".yml", ".yaml", ".ini", ".cfg", ".toml", ".properties"}
CODE_EXT = {".py", ".js", ".ts", ".mjs", ".html", ".json", ".sh", ".ipynb", ".jsx", ".tsx"} | CONF_EXT
MAX_BYTES = 1 << 20
MASK = "(경로 가림: 개인정보 포함)"
ENV_RX = re.compile(r"\.env(\.(?!example$|sample$|template$|dist$|.*\.example$).+)?")
# 키 이름: 뒤에 _suffix나 대문자 suffix만 허용(secretary 제외), tokenizer, tokens, token_type 제외. ponytail: .example/.sample/.template/.dist는 확장자 기준으로 이미 대상 밖
KEY = r"(?i:secret|passw(?:or)?d|api[_-]?key|private[_-]?key|access[_-]?key|token(?!i[sz]er|s\b|s_|[_-]?type))(?![_-]?(?i:name|ref|url|uri|file|path|dir)\b)(?:[_-]\w*|[A-Z0-9]\w*)?"
SECRET_RULES = [
    ("하드코딩 비밀값", re.compile(KEY + r"""\\?["']?\s*[:=]\s*\\?["'][^"'\s\\]{6,}\\?["']""")),
    ("하드코딩 개인키", re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----")),
    ("환경변수 기본값에 비밀값", re.compile(r"""(?i)(environ\.get|getenv)\(\s*["'][^"']*(secret|passw|key|token)[^"']*["']\s*,\s*["'][^"'\s]{6,}["']""")),
]
UNQUOTED = ("하드코딩 비밀값(따옴표 없음)", re.compile(
    r"""^(?!\s*[#;]).*?""" + KEY + r"""["']?\s*[:=]\s*(?!\$\{|<|os\.environ|env\()[^"'\s\\]{8,}"""))
DEPS_IGNORE = {"setuptools", "pip", "wheel", "pkg_resources"}
IMPORT_TO_PKG = {"sklearn": "scikit-learn", "yaml": "pyyaml", "PIL": "pillow", "cv2": "opencv-python|opencv-python-headless",
                 "dotenv": "python-dotenv", "bs4": "beautifulsoup4", "jwt": "pyjwt", "dateutil": "python-dateutil",
                 "multipart": "python-multipart"}


def F(loc, what, fix, sev="FAIL"):
    return (sev, loc, what, fix)


def split(s):
    return [x.strip() for x in (s or "").split(",") if x.strip()]


def norm_path(p):
    return os.path.normpath(p).replace(os.sep, "/").strip("/")


def git(root, *args):
    try:
        r = subprocess.run(["git", "-c", "core.quotepath=off", "-C", root] + list(args),
                           capture_output=True, text=True, encoding="utf-8", errors="replace")
        return r.returncode, r.stdout
    except OSError:
        return 127, ""


def status_paths(out):
    return [l[3:].strip('"') for l in out.splitlines() if l.strip()]


def is_code(f):
    b = os.path.basename(f)
    return os.path.splitext(b)[1] in CODE_EXT or b.startswith("Dockerfile")


def is_test(f):
    b = os.path.basename(f)
    return (b.startswith("test_") and b.endswith(".py")) or b.endswith("_test.py") or "tests" in f.split("/")[:-1]


def unscanned(fs, kind, fix):
    return F(f"(검사 못한 파일 {len(fs)}개)", ", ".join(fs[:10]) + (" 외" if len(fs) > 10 else "") + f" 는 읽지 못해 {kind} 검사를 하지 못함",
             fix, "WARN")


class Ctx:
    def __init__(self, a):
        self.a, self.root, self._cache, self.pii_vals = a, os.path.abspath(a.root), {}, set()
        self.raw = [norm_path(self.rel(p)) for p in a.raw]
        self.src = self.rel(a.pii_source) if a.pii_source else None
        ex = [norm_path(p) for p in a.exclude]
        self.names = (SKIP_DIRS - {"work"}) | set(ex)  # work/는 secrets만 본다
        self.paths = self.raw + ex
        self.sfiles = sorted(self._walk())
        self.files = [f for f in self.sfiles if f.split("/")[0] != "work"]

    def rel(self, p):
        """절대경로는 그대로, 상대경로는 root 기준을 먼저 보고 없으면 cwd 기준. root 기준 posix relpath로 돌려준다."""
        q = p if os.path.isabs(p) else next((x for x in (os.path.join(self.root, p), os.path.abspath(p)) if os.path.exists(x)),
                                            os.path.join(self.root, p))
        try:
            return os.path.relpath(q, self.root).replace(os.sep, "/")
        except ValueError:  # 다른 드라이브
            return q.replace(os.sep, "/")

    def show(self, p):
        return MASK if any(v in p for v in self.pii_vals) else p

    def _ex(self, rel):
        return any(rel == p or rel.startswith(p + "/") for p in self.paths)

    def _walk(self):
        for d, dirs, fs in os.walk(self.root):
            rd = os.path.relpath(d, self.root).replace(os.sep, "/")
            join = lambda x: x if rd == "." else rd + "/" + x
            dirs[:] = [x for x in dirs if x not in self.names and not self._ex(join(x))]
            for f in fs:
                if f not in self.names and not self._ex(join(f)):
                    yield join(f)

    def stream(self, rel):
        """텍스트 줄을 하나씩(크기 제한 없음). 바이너리(NUL)면 ValueError, 읽기 실패는 OSError."""
        with open(os.path.join(self.root, rel), "rb") as fh:
            if b"\0" in fh.read(8192):
                raise ValueError("binary")
            fh.seek(0)
            for b in fh:
                if b"\0" in b:
                    raise ValueError("binary")
                try:
                    yield b.decode("utf-8-sig").rstrip("\r\n")
                except UnicodeDecodeError:
                    yield b.decode("cp949", "replace").rstrip("\r\n")

    def lines(self, rel):
        """텍스트 줄 목록. 바이너리, 1 MB 초과, 읽기 실패는 None."""
        if rel not in self._cache:
            try:
                ok = os.path.getsize(os.path.join(self.root, rel)) <= MAX_BYTES
                self._cache[rel] = list(self.stream(rel)) if ok else None
            except (OSError, ValueError):
                self._cache[rel] = None
        return self._cache[rel]

    def grep(self, files, rx):
        """(파일, 줄번호) 목록. 주석 줄은 건너뛴다."""
        for f in files:
            for i, l in enumerate(self.lines(f) or [], 1):
                if rx.search(l) and not l.lstrip().startswith(("#", "//")):
                    yield f, i


def required_files(c):
    req = split(c.a.require)
    if not req:
        return 0, [F("(전체)", "필수 파일 대상 0개는 통과가 아니다", "--require에 파일 이름을 준다(기본값을 쓰려면 옵션을 뺀다)")]
    bad = [F(f, "필수 파일 없음", f"{f}를 루트에 만든다(과제가 다른 이름을 정했으면 --require로 덮어쓴다)")
           for f in req if not os.path.exists(os.path.join(c.root, f))]
    return len(req), bad


def notes_sections(c):
    ls = c.lines("NOTES.md")
    if ls is None:
        return 0, [F("NOTES.md", "없거나 읽을 수 없음", "NOTES.md를 만들고 5개 절 제목을 넣는다")]
    heads, fence = [], False
    for i, l in enumerate(ls):
        fence ^= l.lstrip().startswith("```")
        m = None if fence else re.match(r"\s{0,3}(#+)\s", l)
        if m:
            heads.append((i, len(m.group(1)), l))
    bad = []
    for k in NOTES_KEYS:
        h = next((x for x in heads if k in x[2]), None)
        if not h:
            bad.append(F("NOTES.md", f"제목 줄에 '{k}' 없음", f"`## {k}` 제목 절을 추가한다"))
        elif k == "결정 카드":
            end = next((x[0] for x in heads if x[0] > h[0] and x[1] <= h[1]), len(ls))
            body = [l for l in ls[h[0] + 1:end] if l.strip() and not re.match(r"\s{0,3}#+\s", l)]
            if not body:
                bad.append(F(f"NOTES.md:{h[0] + 1}", "결정 카드 절이 비어 있음",
                             "결정 / 고른 안 / 대안 2개 / 동작 설명 / 뒤집히는 조건 / 파라미터 현재 값을 1장 이상 쓴다"))
    return len(NOTES_KEYS), bad


def secrets(c):
    fs = [f for f in c.sfiles if is_code(f) and not is_test(f)]
    if not fs:
        return 0, [F("(전체)", "검사 대상 코드 파일 0개는 통과가 아니다", "--root와 --exclude를 확인하고 코드가 있는 폴더에서 실행한다")]
    bad, skipped = [], []
    for f in fs:
        rules = SECRET_RULES + ([UNQUOTED] if os.path.splitext(f)[1] in CONF_EXT else [])
        try:
            for i, l in enumerate(c.stream(f), 1):
                name = next((n for n, rx in rules if rx.search(l)), None)
                if name:
                    bad.append(F(f"{f}:{i}", f"{name} 의심", "값을 코드에서 지우고 .env(gitignore)에서 os.environ으로 읽는다. .env.example에는 가짜 값만 둔다"))
        except (OSError, ValueError):
            skipped.append(f)
    if skipped:
        bad.append(unscanned(skipped, "비밀값", "해당 파일에 비밀값이 없는지 직접 확인한다"))
    return len(fs), bad


def env_files(c):
    tr = set(git(c.root, "ls-files")[1].splitlines())
    un = git(c.root, "ls-files", "-o", "--exclude-standard")[1].splitlines()
    cand = sorted(p for p in tr | set(un) | set(c.files) if ENV_RX.fullmatch(os.path.basename(p)))
    bad = []
    for t in cand:
        if t in tr:
            bad.append(F(t, ".env 파일이 git에 추적됨", f"`git rm --cached {t}` 후 커밋한다. 서비스 비밀값은 폐기하고 새로 발급한다. 가명 ID 키는 재발급하지 말고(모든 ID가 바뀜) 사람에게 보고한다"))
        elif git(c.root, "check-ignore", "-q", "--", t)[0] != 0:
            bad.append(F(t, ".env 파일이 .gitignore에 없음", f"커밋 금지. .gitignore에 `{os.path.basename(t)}` 한 줄을 추가한다(모든 하위 폴더는 `**/.env`)"))
    fs = [f for f in c.files if is_code(f) and not is_test(f)]
    if not os.path.exists(os.path.join(c.root, ".env.example")):
        hit = next(iter(c.grep(fs, re.compile(r"os\.environ|getenv|process\.env"))), None)
        if hit:
            bad.append(F(f"{hit[0]}:{hit[1]}", "환경변수를 읽는데 .env.example이 없음", ".env.example에 변수 이름과 가짜 값을 적어 커밋한다", "WARN"))
    return len(fs) + len(cand), bad


def pii_leak(c):
    a = c.a
    if not a.pii_source:
        return None, "--pii-source, --pii-cols를 주면 검사"
    src = os.path.join(c.root, c.src)
    try:
        with open(src, "rb") as fh:
            b = fh.read()
        try:
            text = b.decode("utf-8-sig")
        except UnicodeDecodeError:
            text = b.decode("cp949")
        rd = csv.DictReader(io.StringIO(text))
        heads = {(h or "").strip(): h for h in rd.fieldnames or []}
        cols = split(a.pii_cols)
        vals = {}
        for row in rd:
            for col in cols:
                v = (row.get(heads[col]) or "").strip() if col in heads else ""
                if len(v) >= a.pii_min_len:
                    vals.setdefault(v, col)
    except (OSError, UnicodeDecodeError, csv.Error) as e:
        return 0, [F(a.pii_source, f"원본 CSV를 읽지 못함({type(e).__name__})", "경로와 인코딩(utf-8-sig, cp949)을 확인한다")]
    bad = [F(a.pii_source, f"열 '{col}'이 헤더에 없음", "열 이름 오타를 고친다") for col in cols if col not in heads]
    if not vals:
        return 0, bad + [F(a.pii_source, "지정 열에서 값 0개", "--pii-cols 열 이름 오타나 --pii-min-len을 확인한다")]
    c.pii_vals = set(vals)
    skip = "" if c.raw else c.src.rpartition("/")[0]  # --raw가 없으면 원본 폴더 전체를 뺀다
    n, unread = 0, []
    for f in c.sfiles:  # work/ 사본도 본다: 식별 열 삭제 실패 흔적이 남는 곳
        if f == c.src or (skip and f.startswith(skip + "/")):
            continue
        try:
            it, i0 = c.stream(f), 0
            for ch in iter(lambda: list(islice(it, 5000)), []):  # 5000줄씩: 덩어리에 값이 있을 때만 줄 단위로 찾음
                blob = "\n".join(ch)
                hits = [v for v in vals if v in blob]
                for i, l in enumerate(ch if hits else [], i0 + 1):
                    cs = sorted({vals[v] for v in hits if v in l})
                    if cs:
                        bad.append(F(f"{f}:{i}", f"원본 열 {','.join(cs)}의 값이 들어 있음", "그 값을 지우고 가명 ID나 집계로 바꾼다(AGENTS.md 데이터 2번)"))
                i0 += len(ch)
            n += 1
        except (OSError, ValueError):
            unread.append(c.show(f))
    if unread:
        bad.append(unscanned(unread, "개인정보", "해당 파일에 개인정보가 없는지 확인하거나 CSV로 내보내 다시 검사한다"))
    if not c.raw:
        bad.append(F(a.pii_source, "--raw 없이 실행해 원본 폴더를 개인정보 검사에서 뺌", "원본 폴더를 --raw로 지정하면 원본 변경 검사도 한다", "WARN"))
    if n == 0:
        bad.append(F("(전체)", "검사 대상 파일 0개는 통과가 아니다", "--root와 --exclude를 확인한다"))
    return n, bad


def raw_unchanged(c):
    if not c.raw:
        return None, "--raw를 주면 검사"
    bad = []
    for p in c.raw:
        if not os.path.exists(os.path.join(c.root, p)):
            bad.append(F(p, "원본 경로가 없음", "--raw 경로 오타를 고친다"))
        elif git(c.root, "ls-files", "--", p)[1].strip() == "":
            rc = git(c.root, "rev-parse", "--is-inside-work-tree")[0]
            bad.append(F(p, "git에 추적되지 않음" if rc == 0 else "git 저장소가 아님",
                         "원본을 처음에 커밋해야 변경 여부를 알 수 있다: git add 후 commit", "WARN" if rc == 0 else "FAIL"))
        else:
            for q in status_paths(git(c.root, "status", "--porcelain", "--", p)[1]):
                bad.append(F(q, "원본이 바뀜", f"`git checkout -- {q}`로 되돌리거나 새로 받은 원본이면 사유를 NOTES.md에 적고 커밋한다"))
    return len(c.raw), bad


def git_clean(c):
    rc, out = git(c.root, "status", "--porcelain", "-uall")
    if rc != 0:
        return 0, [F("(전체)", "git 저장소가 아님", "git init 후 커밋한다")]
    n = len(git(c.root, "ls-files")[1].splitlines())
    bad = [F(c.show(q), "커밋되지 않음", "커밋 금지. .gitignore에 추가한다" if ENV_RX.fullmatch(os.path.basename(q))
             else "git add <이 경로>; git commit -m \"무엇을, 왜\" (git add -A 금지)") for q in status_paths(out)]
    if n == 0:
        bad.append(F("(전체)", "커밋된 파일 0개는 통과가 아니다", "작업물을 커밋한다"))
    return n, bad


def debug_mode(c):
    fs = [f for f in c.files if os.path.splitext(f)[1] in (".py", ".js", ".html")]
    if not fs:
        return None, "검사 대상 파일 0개"
    py = [f for f in fs if f.endswith(".py")]
    bad = [F(f"{f}:{i}", "debug=True", "debug를 끄거나 환경변수로 받는다(기본 False)")
           for f, i in c.grep(py, re.compile(r"\b(?i:debug)\s*=\s*True\b"))]
    bad += [F(f"{f}:{i}", "innerHTML 대입", "textContent를 쓴다", "WARN")
            for f, i in c.grep([f for f in fs if not f.endswith(".py")], re.compile(r"innerHTML\s*\+?="))]
    return len(fs), bad


def deps(c):
    std = getattr(sys, "stdlib_module_names", None)
    py = [f for f in c.files if f.endswith(".py") and os.path.basename(f) != "setup.py"]
    if std is None or not py:
        return None, "stdlib_module_names 없는 Python(3.10 미만)" if py else ".py 파일 0개"
    local = {os.path.splitext(os.path.basename(f))[0] for f in py}.union(*[set(f.split("/")[:-1]) for f in py])
    mods, bad = {}, []
    for f in py:
        try:
            tree = ast.parse("\n".join(c.lines(f) or []))
        except (SyntaxError, ValueError):
            bad.append(F(f, "구문 분석 실패, import를 점검하지 못함", "문법 오류를 고치거나 파이썬 버전을 확인한다", "WARN"))
            continue
        for nd in tree.body:
            names = [x.name for x in nd.names] if isinstance(nd, ast.Import) else \
                [nd.module] if isinstance(nd, ast.ImportFrom) and nd.level == 0 and nd.module else []
            for n in names:
                mods.setdefault(n.split(".")[0], f"{f}:{nd.lineno}")
    reqs, have = set(), c.lines("requirements.txt")
    ls = list(have or [])
    for l in list(ls):  # `-r 다른파일`은 root 기준으로 1단계만 따라 읽는다
        m = re.match(r"\s*(?:-r|--requirement)[\s=]*(\S+)", l)
        ls += c.lines(norm_path(m.group(1))) or [] if m else []
    for l in ls:
        m = re.match(r"[A-Za-z0-9][A-Za-z0-9._-]*", l.strip()) if not l.strip().startswith(("#", "-")) else None
        if m:
            reqs.add(re.sub(r"[-_.]+", "-", m.group(0).lower()))
    for m, loc in sorted(mods.items()):
        pk = [re.sub(r"[-_.]+", "-", p.lower()) for p in IMPORT_TO_PKG.get(m, m).split("|")]
        if m in std or m in local or m in DEPS_IGNORE or any(r == p or r.startswith(p + "-") for p in pk for r in reqs):
            continue
        bad.append(F(loc, f"import {m}: " + ("requirements.txt에 없음" if have is not None else "requirements.txt 파일이 없음"),
                     f"requirements.txt에 `{pk[0]}==버전` 줄을 추가한다(`pip freeze | grep -i {pk[0]}`)"))
    return len(py), bad


CHECKS = [("required_files", required_files), ("notes_sections", notes_sections), ("secrets", secrets),
          ("env_files", env_files), ("pii_leak", pii_leak), ("raw_unchanged", raw_unchanged),
          ("git_clean", git_clean), ("debug_mode", debug_mode), ("deps", deps)]


def main(argv=None):
    for s in (sys.stdout, sys.stderr):
        if hasattr(s, "reconfigure"):
            s.reconfigure(encoding="utf-8")
    ap = argparse.ArgumentParser(description="제출 전 점검: 실패하면 파일:줄과 고치는 법을 출력한다")
    ap.add_argument("--root", default=".")
    ap.add_argument("--require", default=DEFAULT_REQUIRE)
    ap.add_argument("--raw", type=split, default=[])
    ap.add_argument("--pii-source")
    ap.add_argument("--pii-cols")
    ap.add_argument("--pii-min-len", type=int, default=3)
    ap.add_argument("--exclude", type=split, default=[])
    a = ap.parse_args(argv)
    if not os.path.isdir(a.root):
        ap.error("--root가 폴더가 아님")
    if a.pii_min_len < 1:
        ap.error("--pii-min-len은 1 이상이어야 함")
    if bool(a.pii_source) != bool(a.pii_cols):
        ap.error("--pii-source와 --pii-cols는 함께 줘야 한다")
    c, cnt, out = Ctx(a), dict(FAIL=0, WARN=0, PASS=0, SKIP=0), []
    for name, fn in CHECKS:
        try:
            n, bad = fn(c)
        except Exception as e:  # 예외 메시지에 값이 섞일 수 있어 종류만 출력
            n, bad = 0, [F("(실행 오류)", f"{name} 검사 중 {type(e).__name__}", "인자와 경로를 확인한다")]
        if n is None:
            st = "SKIP"
            out.append(f"[SKIP] {name}: {bad}")
        else:
            bad.sort(key=lambda x: x[0] != "FAIL")
            st = "FAIL" if bad and bad[0][0] == "FAIL" else "WARN" if bad else "PASS"
            out.append(f"[{st}] {name}: 검사 대상 {n}개, 문제 {len(bad)}개")
            for sev, loc, what, fix in bad[:20]:
                out.append(f"  - {loc} {'' if sev == st else '(경고) '}{what} → 고치는 법: {fix}")
            if len(bad) > 20:
                out.append(f"  - 외 {len(bad) - 20}건")
        cnt[st] += 1
    # 모든 검사가 끝난 뒤 출력: pii 값이 경로나 문구에 섞였으면 어느 검사 출력이든 가린다
    vals = sorted(c.pii_vals, key=len, reverse=True)
    for line in out:
        for v in vals:
            line = line.replace(v, "(가림)")
        print(line)
    print(" / ".join(f"{k} {v}" for k, v in cnt.items()))
    return 1 if cnt["FAIL"] else 0


if __name__ == "__main__":
    sys.exit(main())
