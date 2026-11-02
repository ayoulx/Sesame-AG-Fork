"""verify.sh 的结构化检查实现。

Bash 负责「重置 → 打补丁 → 再打一次」的流程，这里负责把结果读成可判定的断言。
每个检查函数返回 (ok, lines)，由 main 汇总，任一失败即非零退出。
"""

from __future__ import annotations

import os
import re
import subprocess
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
STATE = os.path.join(ROOT, "customizations", ".state")
PATCHES = os.path.join(ROOT, "customizations", "patches")

TEXTUAL_SUFFIXES = (".kt", ".kts", ".xml", ".yml", ".yaml", ".pro", ".toml")

# 占位符只认「注释里的 TODO/FIXME/XXX」与 Kotlin 的 TODO() 调用；
# 任务状态字面量（"TODO" -> ...）是业务值，不能算占位。
PLACEHOLDER = re.compile(r"(?://|#|/\*|\*)\s*(?:TODO|FIXME|XXX)\b|\bTODO\(")

# 这些路径属于 fork 自身的基础设施，不参与「补丁不许误伤上游」的对账
ORCHESTRATION_PREFIXES = (
    "customizations/",
    "keystore/",
    ".github/workflows/build-fork.yml",
)


def _run(args: list[str]) -> str:
    return subprocess.run(args, cwd=ROOT, capture_output=True, text=True, check=True).stdout


def _state(name: str) -> list[str]:
    path = os.path.join(STATE, name)
    if not os.path.isfile(path):
        return []
    with open(path, encoding="utf-8") as fp:
        return [line.strip() for line in fp if line.strip()]


def touched() -> set[str]:
    result: set[str] = set()
    for name in os.listdir(STATE) if os.path.isdir(STATE) else []:
        if name.startswith("touched-") and name.endswith(".txt"):
            result.update(_state(name))
    return result


def created() -> set[str]:
    result: set[str] = set()
    for name in os.listdir(STATE) if os.path.isdir(STATE) else []:
        if name.startswith("created-") and name.endswith(".txt"):
            result.update(_state(name))
    return result


def check_scope() -> tuple[bool, list[str]]:
    """补丁动过的文件必须与 git 报告完全一致（不多不少）。"""
    expected = touched()
    raw = _run(["git", "status", "--porcelain", "--untracked-files=all"])
    actual: set[str] = set()
    for line in raw.splitlines():
        path = line[3:].strip()
        if " -> " in path:
            path = path.split(" -> ", 1)[1].strip()
        # fork 自身的基础设施不属于「补丁改动」的范畴
        if path.startswith(ORCHESTRATION_PREFIXES):
            continue
        actual.add(path)

    ok = expected == actual
    lines = []
    if ok:
        lines.append(f"改动范围与声明一致，共 {len(expected)} 个文件")
    else:
        for item in sorted(actual - expected):
            lines.append(f"意外改动: {item}")
        for item in sorted(expected - actual):
            lines.append(f"声明了但未产生改动: {item}")
    return ok, lines


def check_idempotent() -> tuple[bool, list[str]]:
    """第二次执行不能改变任何字节。"""
    manifest_path = os.path.join(STATE, "hashes.txt")
    if not os.path.isfile(manifest_path):
        return False, ["缺少 .state/hashes.txt（第一轮快照）"]
    with open(manifest_path, encoding="utf-8") as fp:
        recorded = _parse_hashes(fp.read())
    current = _hash_manifest()
    if recorded == current:
        return True, [f"重复执行无副作用，{len(current)} 个文件哈希未变"]
    changed = sorted(set(recorded) ^ set(current))
    details = [f"{path}: {recorded.get(path, '缺失')} -> {current.get(path, '缺失')}" for path in changed]
    return False, [f"重复执行产生了变更: {line}" for line in details[:10]]


def _parse_hashes(text: str) -> dict[str, str]:
    result = {}
    for line in text.splitlines():
        parts = line.split()
        if len(parts) >= 2:
            result[parts[-1].lstrip("*")] = parts[0]
    return result


def _hash_manifest() -> dict[str, str]:
    import hashlib

    entries = {}
    for rel in sorted(touched()):
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            entries[rel] = "<missing>"
            continue
        with open(path, "rb") as fp:
            entries[rel] = hashlib.sha256(fp.read()).hexdigest()
    return entries


def eol_style(raw: bytes) -> str:
    lf = raw.count(b"\n")
    crlf = raw.count(b"\r\n")
    if lf == 0:
        return "NONE"
    if crlf == 0:
        return "LF"
    if crlf == lf:
        return "CRLF"
    return "MIXED"


def snapshot_eol() -> int:
    """打补丁前记录每个源文件的原始行尾风格，供 check_eol 对比。"""
    os.makedirs(STATE, exist_ok=True)
    rows = []
    for base, _, files in os.walk(os.path.join(ROOT, "app", "src")):
        for name in files:
            if not name.endswith(TEXTUAL_SUFFIXES):
                continue
            path = os.path.join(base, name)
            with open(path, "rb") as fp:
                rows.append(f"{os.path.relpath(path, ROOT).replace(chr(92), '/')} {eol_style(fp.read())}")
    with open(os.path.join(STATE, "eol-before.txt"), "w", encoding="utf-8", newline="\n") as fp:
        fp.write("\n".join(sorted(rows)) + "\n")
    print(f"已记录 {len(rows)} 个源文件的行尾风格")
    return 0


def check_eol() -> tuple[bool, list[str]]:
    """行尾必须与打补丁前一致：原来是 LF 就还是 LF，原来是 CRLF 就还是 CRLF。"""
    snapshot_path = os.path.join(STATE, "eol-before.txt")
    before = {}
    if os.path.isfile(snapshot_path):
        with open(snapshot_path, encoding="utf-8") as fp:
            for line in fp:
                parts = line.split()
                if len(parts) == 2:
                    before[parts[0]] = parts[1]

    problems = []
    files = [rel for rel in sorted(touched()) if rel.endswith(TEXTUAL_SUFFIXES)]
    for rel in files:
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            problems.append(f"{rel}: 文件不存在")
            continue
        with open(path, "rb") as fp:
            raw = fp.read()
        after = eol_style(raw)
        lone_cr = raw.count(b"\r") - raw.count(b"\r\n")
        if lone_cr:
            problems.append(f"{rel}: {lone_cr} 处孤立 CR")
        expected = before.get(rel)
        if expected is None:
            # 新增文件：必须是单一的 LF 或 CRLF，不能混排
            if after == "MIXED":
                problems.append(f"{rel}: 新增文件行尾混排")
            continue
        if expected != "MIXED" and after != expected:
            problems.append(f"{rel}: 行尾由 {expected} 变成 {after}")
    if problems:
        return False, problems
    return True, [f"行尾无损：{len(files)} 个文本文件风格未变"]


def check_markers() -> tuple[bool, list[str]]:
    """每个具名标记只应出现一次，且至少有一个标记。"""
    seen: dict[str, int] = {}
    for rel in sorted(touched()):
        if not rel.endswith(TEXTUAL_SUFFIXES):
            continue
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fp:
            text = fp.read()
        for marker in re.findall(r"\[fork:[A-Za-z0-9_]+:[A-Za-z0-9_]+\]", text):
            seen[marker] = seen.get(marker, 0) + 1

    duplicated = [f"{marker} 出现 {count} 次" for marker, count in seen.items() if count > 1]
    if not seen:
        return False, ["未找到任何 [fork:tag:name] 标记"]
    if duplicated:
        return False, duplicated
    return True, [f"幂等标记齐全：{len(seen)} 个标记各出现 1 次"]


def _strip_kotlin(text: str) -> str:
    """去掉注释与字符串字面量，只留结构符号。"""
    out = []
    i = 0
    length = len(text)
    while i < length:
        char = text[i]
        if char == "/" and i + 1 < length and text[i + 1] == "/":
            while i < length and text[i] != "\n":
                i += 1
        elif char == "/" and i + 1 < length and text[i + 1] == "*":
            i += 2
            while i + 1 < length and not (text[i] == "*" and text[i + 1] == "/"):
                i += 1
            i += 2
        elif char == '"' and text[i : i + 3] == '"""':
            i += 3
            while i + 2 < length and text[i : i + 3] != '"""':
                i += 1
            i += 3
        elif char in "\"'":
            quote = char
            i += 1
            while i < length and text[i] != quote:
                i += 2 if text[i] == "\\" else 1
            i += 1
        else:
            out.append(char)
            i += 1
    return "".join(out)


def check_balance() -> tuple[bool, list[str]]:
    """括号必须配平——编译前的最后一道结构防线。"""
    pairs = {"(": ")", "{": "}", "[": "]"}
    closers = {value: key for key, value in pairs.items()}
    problems = []
    files = [rel for rel in sorted(touched()) if rel.endswith(".kt")]
    for rel in files:
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8") as fp:
            stripped = _strip_kotlin(fp.read())
        stack: list[tuple[str, int]] = []
        line = 1
        broken = None
        for char in stripped:
            if char == "\n":
                line += 1
            elif char in pairs:
                stack.append((char, line))
            elif char in closers:
                if not stack or stack[-1][0] != closers[char]:
                    broken = f"{rel}:{line} 出现未匹配的 '{char}'"
                    break
                stack.pop()
        if broken:
            problems.append(broken)
        elif stack:
            opener, at = stack[-1]
            problems.append(f"{rel}:{at} 的 '{opener}' 未闭合")
    if problems:
        return False, problems
    return True, [f"结构完整：{len(files)} 个 Kotlin 文件括号配平"]


def check_payload() -> tuple[bool, list[str]]:
    """payload 里的每个文件都必须被某个补丁引用，避免留下死文件。"""
    payload_dir = os.path.join(PATCHES, "payload")
    if not os.path.isdir(payload_dir):
        return True, ["没有 payload 目录"]

    patch_text = ""
    for name in sorted(os.listdir(PATCHES)):
        if name.endswith(".py"):
            with open(os.path.join(PATCHES, name), encoding="utf-8") as fp:
                patch_text += fp.read()

    orphans = []
    for base, _, files in os.walk(payload_dir):
        for name in files:
            rel_payload = os.path.relpath(os.path.join(base, name), payload_dir).replace("\\", "/")
            if f'"{rel_payload}"' not in patch_text and f'"{name}"' not in patch_text:
                orphans.append(os.path.relpath(os.path.join(base, name), ROOT).replace("\\", "/"))
    if orphans:
        return False, [f"未被引用的 payload: {item}" for item in orphans]
    return True, ["payload 全部被补丁引用"]


def check_no_placeholders() -> tuple[bool, list[str]]:
    """只看补丁新增的上游行：上游自带的待办不是我们的债，基础设施文件也不参与。

    占位判定落在注释或 ``TODO()`` 调用上：任务状态字面量（``"TODO" -> ...``）
    是业务值，不算占位。
    """
    bad = []

    diff = _run(["git", "diff", "-U0", "--no-color"])
    current = ""
    for line in diff.splitlines():
        if line.startswith("+++ b/"):
            current = line[6:].strip()
        elif line.startswith("+") and not line.startswith("+++"):
            if current.startswith(ORCHESTRATION_PREFIXES):
                continue
            if PLACEHOLDER.search(line):
                bad.append(f"{current}: {line[1:].strip()[:70]}")

    for rel in sorted(created()):
        if not rel.endswith(TEXTUAL_SUFFIXES):
            continue
        path = os.path.join(ROOT, rel)
        if not os.path.isfile(path):
            continue
        with open(path, encoding="utf-8", errors="replace") as fp:
            for number, line in enumerate(fp, 1):
                if PLACEHOLDER.search(line):
                    bad.append(f"{rel}:{number} 残留 {line.strip()[:60]}")

    if bad:
        return False, bad
    return True, ["新增内容无 TODO/FIXME 占位"]


CHECKS = [
    ("改动范围", check_scope),
    ("幂等性", check_idempotent),
    ("行尾无损", check_eol),
    ("幂等标记", check_markers),
    ("结构完整", check_balance),
    ("payload 引用", check_payload),
    ("无占位残留", check_no_placeholders),
]


def main() -> int:
    failed = 0
    for title, check in CHECKS:
        ok, lines = check()
        print(f"[{'OK ' if ok else 'FAIL'}] {title}")
        for line in lines:
            print(f"       {line}")
        if not ok:
            failed += 1
    print()
    print("自检通过" if failed == 0 else f"自检失败：{failed} 项未通过")
    return 0 if failed == 0 else 1


if __name__ == "__main__":
    if len(sys.argv) > 1 and sys.argv[1] == "snapshot":
        sys.exit(snapshot_eol())
    sys.exit(main())
