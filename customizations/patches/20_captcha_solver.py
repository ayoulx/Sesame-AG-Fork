#!/usr/bin/env python3
"""滑块验证（移植自 Fansirsqi-Sesame-TK）。

新增 hook/captcha 下的实现文件，并在 ApplicationHook 里挂一处初始化调用。
参考实现里的全量 Dialog 构造监听、shell 兜底滑动、UI 层阻断 show() 三条路径未采用：
前者代价过大、后者需要 root 或系统权限，且阻断 show() 与滑动自相矛盾，属死代码。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "captcha"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"
CAPTCHA = SRC + "hook/captcha/"

FILES = [
    ("SimpleViewImage.kt", "SimpleViewImage.kt"),
    ("SimpleXpathParser.kt", "SimpleXpathParser.kt"),
    ("ViewHierarchyAnalyzer.kt", "ViewHierarchyAnalyzer.kt"),
    ("MotionEventSimulator.kt", "MotionEventSimulator.kt"),
    ("SimplePageManager.kt", "SimplePageManager.kt"),
    ("SlideCaptchaHandler.kt", "SlideCaptchaHandler.kt"),
    ("CaptchaSolver.kt", "CaptchaSolver.kt"),
]

IMPORT_ANCHOR = "import io.github.aoguai.sesameag.hook.XposedEnv.processName"
IMPORT_SNIPPET = "\nimport io.github.aoguai.sesameag.hook.captcha.CaptchaSolver // [fork:captcha:import]"

INIT_ANCHOR = "                    initVersionInfo(packageName)"
INIT_SNIPPET = (
    "\n                    // [fork:captcha:install] 开关与版本门禁均在 CaptchaSolver 内部判定\n"
    "                    CaptchaSolver.install(classLoader!!)"
)


def apply(patch):
    for name, payload in FILES:
        patch.add_file(CAPTCHA + name, "captcha/" + payload)

    hook = patch.edit(SRC + "hook/ApplicationHook.kt")
    hook.insert_after(IMPORT_ANCHOR, IMPORT_SNIPPET, "import")
    hook.insert_after(INIT_ANCHOR, INIT_SNIPPET, "install")


if __name__ == "__main__":
    run(TAG, apply)
