"""锚点补丁工具箱。

设计约束（与本仓库的 fork 规则一一对应）：
1. 唯一原文定位：每个锚点在全文中必须恰好出现 1 次，否则直接失败，不做模糊匹配。
2. 幂等：每处改动都带 ``[fork:<tag>:<name>]`` 标记，重复执行只做检测不重复写入。
3. CRLF 无损：读写都按目标文件原有行尾风格还原（CRLF 文件改完仍是 CRLF）。
4. 只允许改动声明过的文件：每次运行会把改动的文件写入 ``.state/touched-<tag>.txt``，
   由 verify.sh 与 ``git status`` 对账。
"""

from __future__ import annotations

import os
import sys

ROOT = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
PATCH_DIR = os.path.join(ROOT, "customizations", "patches")
PAYLOAD_DIR = os.path.join(PATCH_DIR, "payload")
STATE_DIR = os.path.join(ROOT, "customizations", ".state")

# 仓库内所有 .kt / .kts / .xml 源文件都是 CRLF；新增文件跟随同一约定。
SOURCE_EOL = "\r\n"


class PatchError(RuntimeError):
    """补丁前置条件不满足（锚点不唯一、目标被外部改动等）。"""


def rel(path: str) -> str:
    return os.path.relpath(path, ROOT).replace("\\", "/")


def _split_eol(text: str) -> tuple[str, str]:
    """返回 (LF 规范化后的正文, 该文件的行尾风格)。"""
    if "\r\n" in text:
        return text.replace("\r\n", "\n"), "\r\n"
    return text.replace("\r", "\n"), "\n"


SOURCE_SUFFIXES = (".kt", ".kts", ".java", ".xml")


def _existing_eol_near(dest: str) -> str:
    """取目标文件邻近既有源文件的行尾风格。

    不能写死 CRLF：仓库对象里存的是 LF（core.autocrlf=true 时提交即归一化），
    Windows 检出成 CRLF、Linux 检出成 LF。新增文件必须跟随「当前检出环境」的
    既有文件风格，否则本地能过、CI 一定报「内容与 payload 不一致」。
    """
    directory = os.path.dirname(dest)
    while True:
        if os.path.isdir(directory):
            for name in sorted(os.listdir(directory)):
                candidate = os.path.join(directory, name)
                if os.path.isfile(candidate) and name.endswith(SOURCE_SUFFIXES):
                    with open(candidate, "rb") as fp:
                        return _split_eol(fp.read().decode("utf-8", "replace"))[1]
        parent = os.path.dirname(directory)
        if parent == directory:
            return SOURCE_EOL
        directory = parent


class Editor:
    """按行尾无损、锚点唯一、带标记的方式编辑单个已存在的源文件。"""

    def __init__(self, path: str, tag: str) -> None:
        self.path = path
        self.tag = tag
        self.display = rel(path)
        with open(path, "rb") as fp:
            raw = fp.read()
        self.bom = raw.startswith(b"\xef\xbb\xbf")
        if self.bom:
            raw = raw[3:]
        text, self.eol = _split_eol(raw.decode("utf-8"))
        self.text = text
        self.written = 0
        self.skipped = 0

    # ---- 内部 ----
    def _marker(self, name: str) -> str:
        return f"[fork:{self.tag}:{name}]"

    def _apply(self, old: str, new: str, name: str) -> None:
        old_n = _split_eol(old)[0]
        new_n, _ = _split_eol(new)
        marker = self._marker(name)

        if marker in self.text:
            self.skipped += 1
            return
        if marker not in new_n:
            raise PatchError(f"{self.display}: 片段 [{name}] 缺少 {marker} 标记，拒绝写入")
        hits = self.text.count(old_n)
        if hits != 1:
            head = old_n.strip().splitlines()[0][:80]
            raise PatchError(f"{self.display}: 锚点 [{name}] 命中 {hits} 次（要求恰好 1 次）: {head!r}")
        self.text = self.text.replace(old_n, new_n, 1)
        self.written += 1

    # ---- 对外 ----
    def replace(self, old: str, new: str, name: str) -> "Editor":
        self._apply(old, new, name)
        return self

    def insert_after(self, anchor: str, snippet: str, name: str) -> "Editor":
        old_n = _split_eol(anchor)[0]
        return self.replace(old_n, old_n + _split_eol(snippet)[0], name)

    def insert_before(self, anchor: str, snippet: str, name: str) -> "Editor":
        old_n = _split_eol(anchor)[0]
        return self.replace(old_n, _split_eol(snippet)[0] + old_n, name)

    def drop(self, old: str, name: str) -> "Editor":
        """原地删掉一段原文（幂等）。

        删除没法在文件里留 ``[fork:tag:name]`` 标记——留了就不叫删干净了。
        所以幂等改由 .state/dropped-<tag>.txt 记录：同一次运行的第二遍能认出来，
        如果基线被重新还原导致原文又出现，也会再删一次。
        """
        old_n = _split_eol(old)[0]
        record = os.path.join(STATE_DIR, f"dropped-{self.tag}.txt")
        applied: set[str] = set()
        if os.path.isfile(record):
            with open(record, encoding="utf-8") as fp:
                applied = {line.strip() for line in fp if line.strip()}

        if name in applied:
            if old_n in self.text:
                self.text = self.text.replace(old_n, "", 1)
                self.written += 1
            else:
                self.skipped += 1
            return self

        hits = self.text.count(old_n)
        if hits != 1:
            head = old_n.strip().splitlines()[0][:80]
            raise PatchError(f"{self.display}: 待删片段 [{name}] 命中 {hits} 次（要求恰好 1 次）: {head!r}")
        self.text = self.text.replace(old_n, "", 1)
        self.written += 1
        os.makedirs(STATE_DIR, exist_ok=True)
        with open(record, "a", encoding="utf-8", newline="\n") as fp:
            fp.write(name + "\n")
        return self

    def replace_all(self, old: str, new: str, name: str) -> "Editor":
        """全文机械改名（同一片段在文件里重复出现时用）。

        ``replace`` 要求锚点唯一，遇到「一个文件里 19 处 ``Log.orchard(`` 要
        统一改名」这种就没法用：逐一写锚点既啰嗦又容易漂移。这里整篇替换，
        幂等判据改成「原文已不再出现」——记在 .state/replaced-<tag>.txt 里。

        与 ``drop`` 同源：不留 ``[fork:...]`` 标记（改名留标记会污染调用点），
        幂等靠状态文件，基线被还原导致原文回来时会再替换一次。
        """
        old_n = _split_eol(old)[0]
        new_n = _split_eol(new)[0]
        if old_n in new_n:
            raise PatchError(f"{self.display}: [{name}] 新内容仍包含原文，会无限替换")
        record = os.path.join(STATE_DIR, f"replaced-{self.tag}.txt")
        applied: set[str] = set()
        if os.path.isfile(record):
            with open(record, encoding="utf-8") as fp:
                applied = {line.strip() for line in fp if line.strip()}

        hits = self.text.count(old_n)
        if name in applied and hits == 0:
            self.skipped += 1
            return self
        if hits == 0:
            raise PatchError(f"{self.display}: 待替换片段 [{name}] 命中 0 次")
        self.text = self.text.replace(old_n, new_n)
        self.written += hits
        if name not in applied:
            os.makedirs(STATE_DIR, exist_ok=True)
            with open(record, "a", encoding="utf-8", newline="\n") as fp:
                fp.write(name + "\n")
        return self

    def save(self) -> None:
        if self.written == 0:
            return
        payload = self.text.replace("\n", self.eol)
        data = payload.encode("utf-8")
        if self.bom:
            data = b"\xef\xbb\xbf" + data
        with open(self.path, "wb") as fp:
            fp.write(data)


class Patcher:
    """一个补丁的执行上下文。"""

    def __init__(self, tag: str) -> None:
        self.tag = tag
        self.touched: set[str] = set()
        self.created: set[str] = set()
        self.removed: set[str] = set()
        self.written = 0
        self.skipped = 0
        self._editors: dict[str, Editor] = {}

    def edit(self, rel_path: str) -> Editor:
        if rel_path in self._editors:
            return self._editors[rel_path]
        path = os.path.join(ROOT, rel_path)
        if not os.path.isfile(path):
            raise PatchError(f"锚点目标不存在: {rel_path}")
        editor = Editor(path, self.tag)
        self._editors[rel_path] = editor
        return editor

    def add_file(self, rel_path: str, payload_name: str) -> None:
        """把 patches/payload/<payload_name> 落盘为 rel_path（幂等）。"""
        src = os.path.join(PAYLOAD_DIR, payload_name)
        if not os.path.isfile(src):
            raise PatchError(f"payload 缺失: {payload_name}")
        with open(src, "rb") as fp:
            body = _split_eol(fp.read().decode("utf-8"))[0]

        dest = os.path.join(ROOT, rel_path)
        if os.path.isfile(dest):
            with open(dest, "rb") as fp:
                # 比对只在 LF 归一化后进行：同一份内容在不同检出环境下行尾不同，
                # 按字节比会把「换行风格差异」误判成「内容被外部改动」。
                if _split_eol(fp.read().decode("utf-8"))[0] == body:
                    self.skipped += 1
                    self.created.add(rel_path)
                    return
            raise PatchError(f"{rel_path}: 已存在且内容与 payload 不一致，请先清理工作区")

        eol = _existing_eol_near(dest)
        os.makedirs(os.path.dirname(dest), exist_ok=True)
        with open(dest, "wb") as fp:
            fp.write(body.replace("\n", eol).encode("utf-8"))
        self.touched.add(rel_path)
        self.created.add(rel_path)
        self.written += 1

    def remove_file(self, rel_path: str) -> None:
        """删除一个上游文件（幂等：文件已不在就算已应用）。

        上游后续版本删掉的模块，这里同步删掉，而不是留着死代码。
        删除清单写进 .state/removed-<tag>.txt，供 checks.py 计入声明集合——
        否则「相对基线的差异」里会多出一批没人认领的删除。
        """
        dest = os.path.join(ROOT, rel_path)
        if not os.path.isfile(dest):
            self.skipped += 1
            self.removed.add(rel_path)
            self._prune_empty_dirs(os.path.dirname(dest))
            return
        os.remove(dest)
        self.removed.add(rel_path)
        self.written += 1
        self._prune_empty_dirs(os.path.dirname(dest))

    @staticmethod
    def _prune_empty_dirs(directory: str) -> None:
        """删文件后顺手清掉空目录。

        git 不跟踪空目录，但工作区里会留下 ``task/antFishPond/`` 这种空壳，
        既看着像漏删，也会让 IDE 显示一个空包。只删确实空的目录，
        且不越过源码根，避免误删其他空目录。
        """
        stop = os.path.normpath(os.path.join(ROOT, "app", "src", "main"))
        directory = os.path.normpath(directory)
        while directory != stop and directory.startswith(stop):
            if not os.path.isdir(directory) or os.listdir(directory):
                return
            os.rmdir(directory)
            directory = os.path.dirname(directory)

    def finish(self) -> int:
        for editor in self._editors.values():
            editor.save()
            if editor.written:
                self.touched.add(editor.display)
            self.written += editor.written
            self.skipped += editor.skipped

        os.makedirs(STATE_DIR, exist_ok=True)
        # 与已有记录取并集：第二遍执行没有新写入，不能把第一遍的声明覆盖成空。
        for prefix, items in (("touched", self.touched), ("created", self.created), ("removed", self.removed)):
            record = os.path.join(STATE_DIR, f"{prefix}-{self.tag}.txt")
            previous = set()
            if os.path.isfile(record):
                with open(record, encoding="utf-8") as fp:
                    previous = {line.strip() for line in fp if line.strip()}
            with open(record, "w", encoding="utf-8", newline="\n") as fp:
                for item in sorted(previous | set(items)):
                    fp.write(item + "\n")

        if self.written == 0:
            print(f"[fork:{self.tag}] 已应用，无需变更（{self.skipped} 处标记命中）")
        else:
            print(f"[fork:{self.tag}] 应用完成：写入 {self.written} 处，跳过 {self.skipped} 处")
        return 0


def run(tag: str, body) -> None:
    patcher = Patcher(tag)
    try:
        body(patcher)
    except PatchError as exc:
        print(f"[fork:{tag}] 失败: {exc}", file=sys.stderr)
        raise SystemExit(1)
    raise SystemExit(patcher.finish())
