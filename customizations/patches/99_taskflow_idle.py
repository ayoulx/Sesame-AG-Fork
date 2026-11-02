#!/usr/bin/env python3
"""修掉任务流的空转，并把每轮逐条跳过日志压成一条。

现场 19:14 那份日志里，运动模块跑了 **64 轮**（轮次上限）什么都没干成：
日志里 `动作成功但未确认进展，执行一次服务端回查` 出现 **66 次**，全在运动频道。

看代码就明白了——那处回查只有注释写着「执行一次」，实现上**没有任何预算**：
回查后拿到的新任务动作键变了，于是再次「成功但未确认进展」，再次回查，
一路空转到 `MAX_DYNAMIC_ROUND_LIMIT=64`。64 轮 × 约 4 秒 ≈ 4 分钟纯空跑，
外加 644 行日志。

顺带的：芝麻信用一轮 17 个任务全部「已失败跳过」时，会逐条打 17 行
`[本轮已跳过complete失败任务：xxx]`。这些跳过信息在「刷新进度」那一行里
本来就有汇总，逐条打纯属重复。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "taskflow"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"

# ---- 1. 回查预算 ----
BUDGET_ANCHOR = "        var tailFollowUpRefreshBudget = 1\n"
BUDGET_SNIPPET = """        // 服务端回查的预算：动作一直「成功但未确认进展」时必须能停下来，// [fork:taskflow:budget]
        // 否则新任务键每轮都变，回查会一路重试到轮次上限（现场见过 64 轮空转）。
        var noProgressRefreshBudget = 1
"""

REFRESH_ANCHOR = """            if (noProgressConfirmationRefreshRequested &&
                !stopCurrentRound &&
                !ApplicationHookConstants.isOffline()
            ) {
                val requiredRound = (round + 1).coerceAtMost(hardRoundLimit)
"""
REFRESH_SNIPPET = """            if (noProgressConfirmationRefreshRequested &&
                !stopCurrentRound &&
                !ApplicationHookConstants.isOffline() &&
                noProgressRefreshBudget > 0
            ) {
                noProgressRefreshBudget-- // [fork:taskflow:budgetuse]
                val requiredRound = (round + 1).coerceAtMost(hardRoundLimit)
"""

# ---- 2. 跳过日志聚合 ----
COUNTER_ANCHOR = """            var progressed = false
            var stopCurrentRound = false
"""
COUNTER_SNIPPET = """            var progressed = false
            var stopCurrentRound = false
            // 逐条跳过日志改成轮末一条汇总，条数都在「刷新进度」里，不必各打一行 // [fork:taskflow:skipcount]
            var skippedFailedCount = 0
            var skippedDeferredCount = 0
            var skippedNoProgressCount = 0
"""

SKIP_FAILED_ANCHOR = (
    '                    adapter.logInfo("${adapter.flowName}[本轮已跳过${action.logName}失败任务：${item.title}]")\n'
)
SKIP_FAILED_SNIPPET = "                    skippedFailedCount++ // [fork:taskflow:skipfailed]\n"

SKIP_DEFERRED_ANCHOR = '                    adapter.logInfo("${adapter.flowName}[本轮已跳过明确延后任务：${item.title}]")\n'
SKIP_DEFERRED_SNIPPET = "                    skippedDeferredCount++ // [fork:taskflow:skipdeferred]\n"

SKIP_NOPROGRESS_ANCHOR = (
    '                    adapter.logInfo("${adapter.flowName}[回查后未确认进展，跳过重复${action.logName}：${item.title}]")\n'
)
SKIP_NOPROGRESS_SNIPPET = "                    skippedNoProgressCount++ // [fork:taskflow:skipnoprogress]\n"

PROGRESS_ANCHOR = """            adapter.logInfo(
                "${adapter.flowName}刷新进度[轮次:$round/$roundLimit]" +
"""
PROGRESS_SNIPPET = """            if (skippedFailedCount + skippedDeferredCount + skippedNoProgressCount > 0) {
                adapter.logInfo(
                    "${adapter.flowName}[本轮跳过：已失败 $skippedFailedCount 个 / 明确延后 $skippedDeferredCount 个 / 回查未确认 $skippedNoProgressCount 个]",
                )
            } // [fork:taskflow:skipsummary]

            adapter.logInfo(
                "${adapter.flowName}刷新进度[轮次:$round/$roundLimit]" +
"""

# ---- 3. status.json 保存降噪 ----
STATUS_ANCHOR = '                Log.record(TAG, "保存 status.json")\n'
STATUS_SNIPPET = """                LogFold.tick("status_save", 20)?.let {
                    Log.record(TAG, "保存 status.json（本次运行第 $it 次）")
                } // [fork:taskflow:statussave]
"""

STATUS_IMPORT_ANCHOR = "import io.github.aoguai.sesameag.util.Log\n"
STATUS_IMPORT_SNIPPET = "import io.github.aoguai.sesameag.util.LogFold // [fork:taskflow:statusimport]\n"


def apply(patch):
    flow = patch.edit(SRC + "task/common/TaskFlow.kt")
    flow.insert_after(BUDGET_ANCHOR, BUDGET_SNIPPET, "budget")
    flow.replace(REFRESH_ANCHOR, REFRESH_SNIPPET, "budgetuse")
    flow.replace(COUNTER_ANCHOR, COUNTER_SNIPPET, "skipcount")
    flow.replace(SKIP_FAILED_ANCHOR, SKIP_FAILED_SNIPPET, "skipfailed")
    flow.replace(SKIP_DEFERRED_ANCHOR, SKIP_DEFERRED_SNIPPET, "skipdeferred")
    flow.replace(SKIP_NOPROGRESS_ANCHOR, SKIP_NOPROGRESS_SNIPPET, "skipnoprogress")
    flow.replace(PROGRESS_ANCHOR, PROGRESS_SNIPPET, "skipsummary")

    status = patch.edit(SRC + "data/Status.kt")
    status.insert_after(STATUS_IMPORT_ANCHOR, STATUS_IMPORT_SNIPPET, "statusimport")
    status.replace(STATUS_ANCHOR, STATUS_SNIPPET, "statussave")


if __name__ == "__main__":
    run(TAG, apply)
