#!/usr/bin/env python3
"""每日随机更换森林装扮（移植自 0.2.6 的 ForestDress）。"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "forestdress"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"
ANTFOREST = SRC + "task/antForest/"

FIELD_ANCHOR = "    internal var forestMarket: BooleanModelField? = null\n"
FIELD_SNIPPET = "    internal var forestDailyDress: BooleanModelField? = null // 每日随机换装\n"

FIELDS_ANCHOR = """        modelFields.addField(BooleanModelField("forestMarket", "森林集市", false).withDesc(
            "执行森林集市任务并领取奖励。"
        ).also { forestMarket = it })
"""

FIELDS_SNIPPET = """        modelFields.addField(BooleanModelField("forestDailyDress", "每日随机更换森林装扮", false).withDesc(
            "从背包里挑一件未过期的装扮穿上，每个部位各一件，穿好回主页确认。"
        ).also { forestDailyDress = it }) // [fork:forestdress:field]
"""

FLOW_ANCHOR = "    if (forestChouChouLe?.value == true) {"
FLOW_SNIPPET = """    // [fork:forestdress:flow] 每日换装放在抽抽乐之前，避免装扮任务被后续流程挤掉
    if (forestDailyDress?.value == true) ForestDress.run()

"""

RPC_ANCHOR = "    fun queryHomePage(source: String? = null): String {"
RPC_SNIPPET = """    // [fork:forestdress:rpc] 森林装扮：背包查询与穿戴
    fun listUserDressForBackpack(positionType: String): String =
        RequestManager.requestString(
            "alipay.antforest.forest.h5.listUserDressForBackpack",
            JSONArray()
                .put(
                    JSONObject()
                        .put("pageQuery", false)
                        .put("positionType", positionType)
                        .put("source", HOME_TASK_SOURCE)
                        .put("version", "20230501"),
                ).toString(),
        )

    fun wearDress(dressTypeList: JSONArray): String =
        RequestManager.requestString(
            "alipay.antforest.forest.h5.wearDress",
            JSONArray()
                .put(
                    JSONObject()
                        .put("dressTypeList", dressTypeList)
                        .put("outBizNo", UUID.randomUUID().toString())
                        .put("source", HOME_TASK_SOURCE),
                ).toString(),
        )

"""

FLAG_ANCHOR = "    /** 森林：双击卡时间槽已消费到的索引 */"
FLAG_SNIPPET = """    /** 森林：每日换装已完成 */
    const val FLAG_ANTFOREST_DAILY_DRESS = "AntForest::dailyDress" // [fork:forestdress:flag]

"""


def apply(patch):
    patch.add_file(ANTFOREST + "ForestDress.kt", "tasks/ForestDress.kt")

    model = patch.edit(ANTFOREST + "AntForest.kt")
    model.insert_after(FIELD_ANCHOR, "    // [fork:forestdress:holder]\n" + FIELD_SNIPPET, "holder")
    model.insert_after(FIELDS_ANCHOR, FIELDS_SNIPPET, "field")

    flow = patch.edit(ANTFOREST + "AntForestWorkflow.kt")
    flow.insert_before(FLOW_ANCHOR, FLOW_SNIPPET, "flow")

    rpc = patch.edit(ANTFOREST + "AntForestRpcCall.kt")
    rpc.insert_before(RPC_ANCHOR, RPC_SNIPPET, "rpc")

    flags = patch.edit(SRC + "data/StatusFlags.kt")
    flags.insert_before(FLAG_ANCHOR, FLAG_SNIPPET, "flag")


if __name__ == "__main__":
    run(TAG, apply)
