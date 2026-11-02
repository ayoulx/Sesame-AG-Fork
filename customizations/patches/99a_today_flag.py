#!/usr/bin/env python3
"""UNKNOWN_NEEDS_REVIEW 的动作当天不再重复尝试（对齐 0.2.6 的当日标记）。

文件名带 a 后缀是为了排序：apply.sh 按字典序执行 patches/*.py，
100_ 会排到 10_ 前面，所以这里不用三位数编号。

0.1.9 里这类失败只在新一轮内存里被 failedActionKeys 挡住，进程重启或跨天就忘了。
现场表现是芝麻信用/芝麻树每天固定刷 105 条 classification=UNKNOWN_NEEDS_REVIEW：
那些是第三方 H5 玩法（去淘宝直播、快手极速版、玩游戏），RPC 根本关不掉，
重试一整年也不会有一次成功。

0.2.6 的做法是 nonRetryableActionFlagPrefix + Status.hasFlagToday：
把「当日不可重试」写进当日标记，跨会话生效、跨天自动失效。
这里把同一套搬到 0.1.9 的 TaskFlow 上。

领取类动作（RECEIVE）不参与拦截：动作被拒不代表奖励不能领。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "todayflag"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"

# ---- 1. 导入与常量 ----
IMPORT_ANCHOR = "import io.github.aoguai.sesameag.hook.ApplicationHookConstants\n"
IMPORT_SNIPPET = "import io.github.aoguai.sesameag.data.Status // [fork:todayflag:import]\n"

CONST_ANCHOR = """        const val MAX_DYNAMIC_ROUND_LIMIT = 64
        const val DYNAMIC_ROUND_LIMIT_EXTRA = 6
"""
CONST_TAIL = """
        // 「当日不可重试」的标记所属模块名。用 Module::Name 约定，
        // Status 会按天清空，第二天自动重来一轮。// [fork:todayflag:const]
        const val NON_RETRYABLE_FLAG_MODULE = "TaskFlow"
"""

# ---- 2. 计数器 ----
COUNTER_ANCHOR = """            var skippedFailedCount = 0
            var skippedDeferredCount = 0
            var skippedNoProgressCount = 0
"""
COUNTER_TAIL = "            var skippedTodayBlockedCount = 0 // [fork:todayflag:count]\n"

# ---- 3. 循环里先查当日标记（整体替换：注释插在锚点两行中间）----
CHECK_ANCHOR = """                val actionKey = adapter.actionKey(item, action)
                if (actionKey in failedActionKeys) {
"""
CHECK_SNIPPET = """                val actionKey = adapter.actionKey(item, action)
                // 当日已被判定「不可重试」的动作直接跳过；领取奖励不拦，避免漏掉已就绪的奖励。
                if (action != TaskFlowAction.RECEIVE && Status.hasFlagToday(todayBlockedFlag(actionKey))) {
                    skippedTodayBlockedCount++
                    roundActions.add(TaskFlowRoundAction("当日不可重试${action.logName}", item.title))
                    continue
                } // [fork:todayflag:check]
                if (actionKey in failedActionKeys) {
"""

# ---- 4. 失败时写当日标记 ----
FAIL_ANCHOR = """                logFailure(item, action, result, failureType, decision)
                adapter.afterFailure(item, action, result, decision)
                failedActionKeys.add(actionKey)
"""
FAIL_TAIL = """                // 玩法本身没有 RPC 闭环（第三方 H5 / 小游戏），今天就不用再试了。
                if (failureType == TaskRpcFailureType.UNKNOWN_NEEDS_REVIEW) {
                    Status.setFlagToday(todayBlockedFlag(actionKey))
                } // [fork:todayflag:write]
"""

# ---- 5. 汇总行带上当日不可重试 ----
SUMMARY_ANCHOR = (
    '                    "${adapter.flowName}[本轮跳过：已失败 $skippedFailedCount 个 / '
    '明确延后 $skippedDeferredCount 个 / 回查未确认 $skippedNoProgressCount 个]",\n'
)
SUMMARY_SNIPPET = (
    '                    "${adapter.flowName}[本轮跳过：已失败 $skippedFailedCount 个 / '
    '明确延后 $skippedDeferredCount 个 / 回查未确认 $skippedNoProgressCount 个 / '
    '当日不可重试 $skippedTodayBlockedCount 个]", // [fork:todayflag:summary]\n'
)

# ---- 5b. 汇总的触发条件也要算上当日不可重试 ----
SUM_COND_ANCHOR = (
    "            if (skippedFailedCount + skippedDeferredCount + skippedNoProgressCount > 0) {\n"
)
SUM_COND_SNIPPET = (
    "            if (skippedFailedCount + skippedDeferredCount + skippedNoProgressCount + "
    "skippedTodayBlockedCount > 0) { // [fork:todayflag:sumcond]\n"
)

# ---- 6. 标记名构造 ----
FLAG_ANCHOR = "    private fun decideFailure(failureType: TaskRpcFailureType): TaskFlowDecision =\n"
FLAG_SNIPPET = """    /**
     * 「当日不可重试」的动作标记名。
     *
     * 走 Status 的 Module::Name 约定，按天生效、跨会话保留；
     * 带上流程名，避免两个模块的同名动作互相拦截。
     */
    private fun todayBlockedFlag(actionKey: String): String =
        "$NON_RETRYABLE_FLAG_MODULE::blocked|${adapter.flowName}|$actionKey" // [fork:todayflag:flag]

    private fun decideFailure(failureType: TaskRpcFailureType): TaskFlowDecision =
"""


def apply(patch):
    flow = patch.edit(SRC + "task/common/TaskFlow.kt")
    flow.insert_before(IMPORT_ANCHOR, IMPORT_SNIPPET, "import")
    flow.insert_after(CONST_ANCHOR, CONST_TAIL, "const")
    flow.insert_after(COUNTER_ANCHOR, COUNTER_TAIL, "count")
    flow.replace(CHECK_ANCHOR, CHECK_SNIPPET, "check")
    flow.insert_after(FAIL_ANCHOR, FAIL_TAIL, "write")
    flow.replace(SUMMARY_ANCHOR, SUMMARY_SNIPPET, "summary")
    flow.replace(SUM_COND_ANCHOR, SUM_COND_SNIPPET, "sumcond")
    flow.replace(FLAG_ANCHOR, FLAG_SNIPPET, "flag")


if __name__ == "__main__":
    run(TAG, apply)
