#!/usr/bin/env python3
"""风控命中时在宿主应用内模拟一次返回。

现场日志里 18:28、18:35、18:44 三次命中 `1009/系统繁忙，请稍后再试`：
`enterOffline` 一开就是 50 分钟冷却，直接把正在跑的任务全部 Job was cancelled。
同一时刻能看到验证码弹窗弹出——受限页面/验证码就是风控的落点，退一步往往能回到正常页面。

新增 hook/HostBack：只对宿主应用自己当前 resumed 的 Activity 投递返回，
走它自己的返回逻辑（androidx 页面用 OnBackPressedDispatcher，其余用返回键事件），
不调用 root 命令、不用 Shizuku、不做系统级输入注入。

开关放在 module_switches.json 的 hostBackOnRisk，默认开启；工具页可关。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "hostback"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"

# ---- 1. 挂载点：跟着 Application.attach 一起注册页面跟踪 ----
ATTACH_ANCHOR = "                    application?.let { PageStructureSnapshotter.install(it) }\n"
ATTACH_SNIPPET = "                    HostBack.attach(application) // [fork:hostback:attach]\n"

# ---- 2. 触发点：进入离线之后 ----
RISK_IMPORT_ANCHOR = "import io.github.aoguai.sesameag.hook.ApplicationHookConstants\n"
RISK_IMPORT_SNIPPET = "import io.github.aoguai.sesameag.hook.HostBack // [fork:hostback:import]\n"

RISK_ANCHOR = """            ApplicationHookConstants.enterOffline(
                ApplicationHookConstants.getOfflineCooldownMs(),
                "auth_like",
                detail,
            )
"""
RISK_SNIPPET = """            ApplicationHookConstants.enterOffline(
                ApplicationHookConstants.getOfflineCooldownMs(),
                "auth_like",
                detail,
            )
            // 1009/系统繁忙 这类拦截通常伴随受限页面或验证码弹窗，退一步往往能回到正常页。
            // 只在宿主应用自己的页面上模拟返回（见 HostBack），不做系统级输入注入。
            if (ModuleSwitches.isHostBackOnRiskEnabled()) {
                HostBack.pressBack("${code.ifBlank { "risk" }}/${message.ifBlank { "unknown" }}")
            } // [fork:hostback:trigger]
"""


def apply(patch):
    patch.add_file(SRC + "hook/HostBack.kt", "hook/HostBack.kt")

    hook = patch.edit(SRC + "hook/ApplicationHook.kt")
    hook.insert_after(ATTACH_ANCHOR, ATTACH_SNIPPET, "attach")

    risk = patch.edit(SRC + "util/RpcOfflineRisk.kt")
    risk.insert_after(RISK_IMPORT_ANCHOR, RISK_IMPORT_SNIPPET, "import")
    risk.replace(RISK_ANCHOR, RISK_SNIPPET, "trigger")


if __name__ == "__main__":
    run(TAG, apply)
