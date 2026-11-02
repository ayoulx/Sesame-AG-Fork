#!/usr/bin/env python3
"""保护地巡护（移植自 0.2.6 的 task/antForestPatrol）。

0.2.6 把巡护从 AntForest 拆成独立模块，并新增「新版巡护」（地图推进/骰子/事件/
保护证书兑换/满星切图）与「动物伙伴」（领取能量、自动派遣）。

改写点（0.1.9 缺失的 0.2.x 基础设施）：
- Log.forestPatrol 频道不存在，统一写森林频道 Log.forest；
- AccountSessionCoordinator.checkCurrentSession(...) !is AccountSessionCheck.Current
  改写为 !isCurrentSession(...)（等价的会话断言）；
- TaskFlowExecutionState 与 TaskFlowEngine 的 executionState 参数不存在，去掉；
- ModelGroup 补 FOREST_PATROL 分组，模型注册表补 AntForestPatrol。

旧版巡护在 0.1.9 的森林页已有等价实现，这里的 legacyPatrol / combineAnimalPiece
默认关闭，避免同一账号重复巡护。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "patrol"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"
PATROL = SRC + "task/antForestPatrol/"

GROUP_ANCHOR = '    /** 森林 */\n    FOREST("FOREST", "森林", "svg/group/forest.svg"),\n'
GROUP_SNIPPET = '    /** 保护地巡护 */\n    FOREST_PATROL("FOREST_PATROL", "保护地巡护", "svg/group/forest.svg"), // [fork:patrol:group]\n'

ORDER_IMPORT_ANCHOR = "import io.github.aoguai.sesameag.task.antForest.AntForest\n"
ORDER_IMPORT_SNIPPET = (
    "import io.github.aoguai.sesameag.task.antForestPatrol.AntForestPatrol // [fork:patrol:orderimport]\n"
)

ORDER_ANCHOR = "        AntForest::class.java,       // 森林\n"
ORDER_SNIPPET = "        AntForestPatrol::class.java, // 保护地巡护 [fork:patrol:order]\n"

PROP_VERSION_ANCHOR = """        val version: String,
        val headers: Map<String, String>? = forestHeaders(source),
"""
PROP_VERSION_SNIPPET = """        val version: String = VERSION, // [fork:patrol:propversion] 巡护道具消费沿用森林版本
        val headers: Map<String, String>? = forestHeaders(source),
"""

FLAG_ANCHOR = '    const val FLAG_ANTFOREST_PATROL_CHANCE_EXCHANGE_LIMIT = "AntForest::exchangePatrolChanceLimit"\n'
FLAG_SNIPPET = (
    '    const val FLAG_ANTFOREST_PATROL_TARGET = "AntForest::patrolTarget" // [fork:patrol:flag]\n'
)

RESERVE_ANCHOR = """    companion object {
        private val TAG = Reserve::class.java.simpleName
"""
RESERVE_SNIPPET = """

        /**
         * 巡护证书兑换：每张地图一份证书。只在服务端明确可申请、且兑换后仍不低于
         * [energyReserve] 时申请一次，避免把森林能量一次消耗到底。
         */
        internal fun exchangeCertificateOnce(projectId: String, itemName: String, energyReserve: Int): Boolean {
            if (energyReserve < 0) return false
            return try {
                val raw = ReserveRpcCall.queryTreeForExchange(projectId)
                val detail = JSONObject(raw).let { it.optJSONObject("resData") ?: it }
                if (!ResChecker.checkRes(TAG, detail)) {
                    Log.error(TAG, "保护证书资格查询失败[$itemName] raw=$detail")
                    return false
                }
                val action = detail.optString("applyAction")
                if (action != "AVAILABLE") {
                    Log.forest("领保护地🏕️[$itemName]#当前不可申请[$action]")
                    return false
                }
                val tree = detail.optJSONObject("exchangeableTree") ?: return false
                if (tree.optBoolean("overLimit") || !tree.optBoolean("hasBudget", true)) {
                    Log.forest("领保护地🏕️[$itemName]#已达上限或项目预算不足")
                    return false
                }
                val cost = tree.optLong("energy", -1L)
                val current = detail.optLong("currentEnergy", -1L)
                if (cost < 0L || current < 0L) {
                    Log.error(TAG, "保护证书能量信息无效[$itemName] raw=$detail")
                    return false
                }
                if (current - cost < energyReserve) {
                    Log.forest("领保护地🏕️[$itemName]#兑换后能量将低于保留值${energyReserve}g，跳过")
                    return false
                }
                if (!Status.canReserveToday(projectId, 1)) {
                    Log.forest("领保护地🏕️[$itemName]#今日申请次数已达上限")
                    return false
                }
                val response = JSONObject(ReserveRpcCall.exchangeTree(projectId))
                val body = response.optJSONObject("resData") ?: response
                if (!ResChecker.checkRes(TAG, body)) {
                    Log.error(TAG, "保护证书兑换失败[$itemName] raw=$body")
                    return false
                }
                Status.reserveToday(projectId, 1)
                val vitality = body.optInt("vitalityAmount", 0)
                Log.forest("领保护地🏕️[$itemName]#兑换证书" + if (vitality > 0) "-活力值+$vitality" else "")
                true
            } catch (t: Throwable) {
                Log.printStackTrace(TAG, "保护证书兑换异常[$itemName]:", t)
                false
            }
        }
        // [fork:patrol:reserve]
"""

def apply(patch):
    patch.add_file(PATROL + "AntForestPatrol.kt", "tasks/patrol/AntForestPatrol.kt")
    patch.add_file(PATROL + "AntForestPatrolRpcCall.kt", "tasks/patrol/AntForestPatrolRpcCall.kt")
    patch.add_file(PATROL + "LegacyPatrolWorkflow.kt", "tasks/patrol/LegacyPatrolWorkflow.kt")
    patch.add_file(PATROL + "MonopolyPatrolWorkflow.kt", "tasks/patrol/MonopolyPatrolWorkflow.kt")

    group = patch.edit(SRC + "model/ModelGroup.kt")
    group.insert_after(GROUP_ANCHOR, GROUP_SNIPPET, "group")

    order = patch.edit(SRC + "model/ModelOrder.kt")
    order.insert_after(ORDER_IMPORT_ANCHOR, ORDER_IMPORT_SNIPPET, "orderimport")
    order.insert_after(ORDER_ANCHOR, ORDER_SNIPPET, "order")

    rpc = patch.edit(SRC + "task/antForest/AntForestRpcCall.kt")
    rpc.replace(PROP_VERSION_ANCHOR, PROP_VERSION_SNIPPET, "propversion")

    flags = patch.edit(SRC + "data/StatusFlags.kt")
    flags.insert_before(FLAG_ANCHOR, FLAG_SNIPPET, "flag")

    reserve = patch.edit(SRC + "task/reserve/Reserve.kt")
    reserve.insert_after(RESERVE_ANCHOR, RESERVE_SNIPPET, "reserve")


if __name__ == "__main__":
    run(TAG, apply)
