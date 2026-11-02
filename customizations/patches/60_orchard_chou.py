#!/usr/bin/env python3
"""芭芭农场抽抽乐（移植自 0.2.6 的 OrchardChouChouLe）。

0.2.6 的实现依赖 TaskFlow 引擎的重试语义开关与执行态快照，0.1.9 的引擎没有这些成员。
这里保留任务流主体（查询 → 完成 → 领机会 → 批量抽奖），去掉仅在 0.2.x 生效的
`continueCurrentRoundOnRetryableFailure` 覆盖与 `executionState` 传参。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "orchardchou"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"
ANTORCHARD = SRC + "task/antOrchard/"

HOLDER_ANCHOR = "    internal lateinit var goldenBeanTreasure: BooleanModelField\n"
HOLDER_SNIPPET = "    internal lateinit var orchardChouChouLe: BooleanModelField // [fork:orchardchou:holder]\n"

FIELD_ANCHOR = """                ).also { goldenBeanTreasure = it },
        )
"""

FIELD_SNIPPET = """        modelFields.addField(
            BooleanModelField("orchardChouChouLe", "抽抽乐 | 自动完成与抽奖", false)
                .withDesc(
                    "自动完成芭芭农场抽抽乐的浏览与任务、领取机会，然后一次性抽完剩余次数。",
                ).also { orchardChouChouLe = it }, // [fork:orchardchou:field]
        )
"""

FLOW_ANCHOR = "    if (goldenBeanTreasure.value == true) {\n"
FLOW_SNIPPET = """    // [fork:orchardchou:flow] 抽抽乐要读活动入口与剩余次数，放在常规任务之后独立处理
    if (orchardChouChouLe.value == true) {
        try {
            runOrchardChouChouLe(userId)
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Log.printStackTrace("OrchardChouChouLe", "run err:", e)
        }
    }

"""

SUCCESS_VISIBLE_ANCHOR = "    private fun isOrchardRpcSuccessResponse(response: JSONObject): Boolean {\n"
SUCCESS_VISIBLE_SNIPPET = (
    "    internal fun isOrchardRpcSuccessResponse(response: JSONObject): Boolean { // [fork:orchardchou:visible]\n"
)

FAILURE_VISIBLE_ANCHOR = "    private fun buildOrchardTaskFailureResult(\n"
FAILURE_VISIBLE_SNIPPET = (
    "    // [fork:orchardchou:visible2]\n    internal fun buildOrchardTaskFailureResult(\n"
)

IMPORT_ANCHOR = "import io.github.aoguai.sesameag.hook.RequestManager\n"
IMPORT_SNIPPET = "import io.github.aoguai.sesameag.util.RandomUtil // [fork:orchardchou:import]\n"

RPC_ANCHOR = "    fun moneyTreeTrigger(): String =\n"
RPC_SNIPPET = """    // [fork:orchardchou:rpc] 农场抽抽乐：活动入口、任务、余额同步与批量抽奖
    fun enterDrawActivity(activityId: String = ""): String {
        val requestData =
            JSONObject().apply {
                put("activityId", activityId)
                put("context", JSONObject().put("appMode", "normal"))
                put("requestType", "RPC")
                put("sceneCode", "ANTORCHARD_DRAW_TIMES")
                put("source", "antorchard")
            }
        return RequestManager.requestString(
            "com.alipay.antiepdrawprod.enterDrawActivityantorchard",
            JSONArray().put(requestData).toString(),
        )
    }

    fun listDrawTasks(): String {
        val requestData =
            JSONObject().apply {
                put("extend", JSONObject().put("appMode", "normal"))
                put("requestType", "RPC")
                put("sceneCode", "ANTORCHARD_DRAW_TIMES_TASK")
                put("source", "antorchard")
            }
        return RequestManager.requestString(
            "com.alipay.antieptask.listTaskantorchard",
            JSONArray().put(requestData).toString(),
        )
    }

    fun finishDrawTask(sceneCode: String, taskType: String): String {
        val requestData =
            JSONObject().apply {
                put("outBizNo", "${taskType}_${System.currentTimeMillis()}_${RandomUtil.getRandomString(8)}")
                put("sceneCode", sceneCode)
                put("source", "antorchard")
                put("taskType", taskType)
            }
        return RequestManager.requestString(
            "com.alipay.antieptask.finishTaskantorchard",
            JSONArray().put(requestData).toString(),
        )
    }

    fun receiveDrawTaskAward(sceneCode: String, taskType: String): String {
        val requestData =
            JSONObject().apply {
                put("ignoreLimit", true)
                put("requestType", "RPC")
                put("sceneCode", sceneCode)
                put("source", "antorchard")
                put("taskType", taskType)
            }
        return RequestManager.requestString(
            "com.alipay.antieptask.receiveTaskAwardantorchard",
            JSONArray().put(requestData).toString(),
        )
    }

    fun syncDrawBalance(activityId: String): String {
        val requestData =
            JSONObject().apply {
                put("activityId", activityId)
                put("context", JSONObject().put("appMode", "normal"))
                put("requestType", "RPC")
                put("sceneCode", "ANTORCHARD_DRAW_TIMES")
                put("source", "taskaward")
            }
        return RequestManager.requestString(
            "com.alipay.antiepdrawprod.drawSyncantorchard",
            JSONArray().put(requestData).toString(),
        )
    }

    fun batchDraw(activityId: String, times: Int, userId: String): String {
        val requestData =
            JSONObject().apply {
                put("activityId", activityId)
                put("requestType", "RPC")
                put("sceneCode", "ANTORCHARD_DRAW_TIMES")
                put("source", "antorchard")
                put("times", times)
                put("userId", userId)
            }
        return RequestManager.requestString(
            "com.alipay.antiepdrawprod.batchDrawantorchard",
            JSONArray().put(requestData).toString(),
        )
    }

"""

FLAG_ANCHOR = (
    "    /** 农场好友助力：好友关系无效前缀 */\n"
    '    const val FLAG_ANTORCHARD_ASSIST_RELATION_INVALID_PREFIX = "orchard::assistRelationInvalid::"\n'
)
FLAG_SNIPPET = """
    /** 农场抽抽乐：今日已探测过新一轮活动 */
    const val FLAG_ANTORCHARD_DRAW_ACTIVITY_PROBED = "AntOrchard::drawActivityProbed" // [fork:orchardchou:flag]
"""


def apply(patch):
    patch.add_file(ANTORCHARD + "OrchardChouChouLe.kt", "tasks/OrchardChouChouLe.kt")

    model = patch.edit(ANTORCHARD + "AntOrchard.kt")
    model.insert_after(HOLDER_ANCHOR, HOLDER_SNIPPET, "holder")
    model.insert_after(FIELD_ANCHOR, FIELD_SNIPPET, "field")
    model.replace(SUCCESS_VISIBLE_ANCHOR, SUCCESS_VISIBLE_SNIPPET, "visible")
    model.replace(FAILURE_VISIBLE_ANCHOR, FAILURE_VISIBLE_SNIPPET, "visible2")

    flow = patch.edit(ANTORCHARD + "AntOrchardWorkflow.kt")
    flow.insert_before(FLOW_ANCHOR, FLOW_SNIPPET, "flow")

    rpc = patch.edit(ANTORCHARD + "AntOrchardRpcCall.kt")
    rpc.insert_after(IMPORT_ANCHOR, IMPORT_SNIPPET, "import")
    rpc.insert_before(RPC_ANCHOR, RPC_SNIPPET, "rpc")

    flags = patch.edit(SRC + "data/StatusFlags.kt")
    flags.insert_after(FLAG_ANCHOR, FLAG_SNIPPET, "flag")


if __name__ == "__main__":
    run(TAG, apply)
