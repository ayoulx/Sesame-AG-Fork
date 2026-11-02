#!/usr/bin/env python3
"""蚂蚁森林无纸阅读（移植自 0.2.6 的 ForestRead / ForestReadRpcCall）。

改写点（均为 0.2.x 独有基础设施的等价替代）：
- 会话断言用 AccountSessionCoordinator 快照，取代 RpcDailyCircuit 的每日熔断；
- 续接计划查重用 PersistentScheduleRegistry.list()，0.1.9 没有 listFresh()；
- UserDataStore.put 不带 requirePersistence 参数，0.1.9 无该重载；
- 去掉 RpcTrafficCapture 的模块自建 HTTP 录制（0.1.9 无此接口，仅影响调试流量面板）。

本补丁的 AntForest 锚点取自 40_forest_dress.py 的产物，须在其之后执行。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "forestread"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"
ANTFOREST = SRC + "task/antForest/"

HOLDER_ANCHOR = "    internal var forestDailyDress: BooleanModelField? = null // 每日随机换装\n"
HOLDER_SNIPPET = "    internal var forestRead: BooleanModelField? = null // 无纸阅读 [fork:forestread:holder]\n"

FIELD_ANCHOR = "        ).also { forestDailyDress = it }) // [fork:forestdress:field]\n"
FIELD_SNIPPET = """        modelFields.addField(BooleanModelField("forestRead", "无纸阅读", false).withDesc(
            "在支付宝里读免费电子书攒森林能量；每章间隔六分钟，读满当日上限即停。"
        ).also { forestRead = it }) // [fork:forestread:field]
"""

FLOW_ANCHOR = "    if (forestDailyDress?.value == true) ForestDress.run()\n"
FLOW_SNIPPET = "\n    // [fork:forestread:flow] 阅读靠持久化续接推进，这里只负责起一轮\n    if (forestRead?.value == true) runForestReadWorkflow()\n"

FLAG_ANCHOR = "    /** 森林：双击卡时间槽已消费到的索引 */"
FLAG_SNIPPET = """    /** 森林：无纸阅读今日已达收益上限 */
    const val FLAG_ANTFOREST_READ_DONE = "AntForest::readDone" // [fork:forestread:flag]

"""

IMPORT_ANCHOR = "import io.github.aoguai.sesameag.task.antFarm.AntFarm\n"
IMPORT_SNIPPET = (
    "import io.github.aoguai.sesameag.task.antForest.AntForest // [fork:forestread:import]\n"
    "import io.github.aoguai.sesameag.task.antForest.FOREST_READ_CHILD_KIND // [fork:forestread:import2]\n"
    "import io.github.aoguai.sesameag.task.antForest.triggerPersistentReadTask // [fork:forestread:import3]\n"
)

ROUTE_ANCHOR = "        if (childKind == AntFarm.PERSISTENT_CHILD_KIND) {\n"
ROUTE_SNIPPET = """        if (childKind == FOREST_READ_CHILD_KIND) {
            // [fork:forestread:route] 无纸阅读按章节续接，到点由这里接着读下一章
            if (targetProcess) {
                val forest = Model.getModel(AntForest::class.java)
                if (forest != null) {
                    if (!forest.isEnable()) {
                        Log.record(TAG, "无纸阅读续接触发时模块已关闭，标记完成: ${schedule.name}")
                        return RouteResult.SKIPPED
                    }
                    return if (forest.triggerPersistentReadTask(schedule.payloadJson, schedule.id, source)) {
                        RouteResult.HANDLED
                    } else {
                        RouteResult.FAILED
                    }
                }
                Log.record(TAG, "森林实例尚未就绪，延后无纸阅读续接: ${schedule.name}")
                return RouteResult.DEFERRED
            }
            return routeResult(dispatchExecute(context, schedule, source, wakenAtTime = false, wakenTime = null))
        }
"""


def apply(patch):
    patch.add_file(ANTFOREST + "ForestRead.kt", "tasks/ForestRead.kt")
    patch.add_file(ANTFOREST + "ForestReadRpcCall.kt", "tasks/ForestReadRpcCall.kt")

    model = patch.edit(ANTFOREST + "AntForest.kt")
    model.insert_after(HOLDER_ANCHOR, HOLDER_SNIPPET, "holder")
    model.insert_after(FIELD_ANCHOR, FIELD_SNIPPET, "field")

    flow = patch.edit(ANTFOREST + "AntForestWorkflow.kt")
    flow.insert_after(FLOW_ANCHOR, FLOW_SNIPPET, "flow")

    flags = patch.edit(SRC + "data/StatusFlags.kt")
    flags.insert_before(FLAG_ANCHOR, FLAG_SNIPPET, "flag")

    router = patch.edit(SRC + "hook/keepalive/ScheduledTaskRouter.kt")
    router.insert_after(IMPORT_ANCHOR, IMPORT_SNIPPET, "import")
    router.insert_before(ROUTE_ANCHOR, ROUTE_SNIPPET, "route")


if __name__ == "__main__":
    run(TAG, apply)
