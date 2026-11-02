#!/usr/bin/env python3
"""模块级开关存储：新增 util/ModuleSwitches.kt，不改动任何既有文件。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "switches"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"


def apply(patch):
    patch.add_file(SRC + "util/ModuleSwitches.kt", "util/ModuleSwitches.kt")


if __name__ == "__main__":
    run(TAG, apply)
