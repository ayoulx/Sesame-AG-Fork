#!/usr/bin/env python3
"""设置页「工具」分组的开关与提示。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "toolui"
SETTINGS = "app/src/main/java/io/github/aoguai/sesameag/ui/screen/content/SettingsContent.kt"

# 「支持」分组是设置页的固定结构，在它前面插入工具分组，位置稳定且不影响既有条目。
ANCHOR = """            item {
                Spacer(Modifier.height(8.dp))
                Text(
                    text = "支持","""

SNIPPET = """            // [fork:toolui:section] 工具分组：滑块验证开关与提示
            captchaToolSection()

"""


def apply(patch):
    patch.add_file(
        "app/src/main/java/io/github/aoguai/sesameag/ui/screen/content/CaptchaToolSection.kt",
        "settings/CaptchaToolSection.kt",
    )
    settings = patch.edit(SETTINGS)
    settings.replace(ANCHOR, SNIPPET + ANCHOR, "section")


if __name__ == "__main__":
    run(TAG, apply)
