#!/usr/bin/env python3
"""金豆商城兑换（移植自 0.2.6 的 goldenBean/GoldenBeanWorkflow.runGoldenBeanMall）。

0.2.6 把金豆夺宝重写成独立 ModelTask，并把集市抽成 ExchangeFetchSession 断点续抓。
0.1.9 的金豆夺宝仍挂在 AntOrchard 下，这里只取「商城兑换」这一个可感知的新玩法：
- 候选列表按同样口径翻页抓取，落 ExchangeOptionsCache（设置页刷新走原广播桥）；
- 兑换保留安全判定（实付/外部下单/权益不明一律只提醒）、余额校验、
  订单号前后比对确认与每日次数计数，不重复提交结果未知的请求。

改写点：SerialTaskQueue 与 RpcDailyCircuit 在 0.1.9 不存在，改用「本轮一次串行」
与 UserMap + 跨天检查作为等价约束；UserDataStore.put 无 requirePersistence 重载。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "goldenbeanmall"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"
ANTORCHARD = SRC + "task/antOrchard/"

IMPORT_ANCHOR = "import io.github.aoguai.sesameag.model.modelFieldExt.IntegerModelField\n"
IMPORT_SNIPPET = (
    "import io.github.aoguai.sesameag.hook.ExchangeOptionsRefreshBridge // [fork:goldenbeanmall:import1]\n"
    "import io.github.aoguai.sesameag.model.modelFieldExt.SelectAndCountModelField // [fork:goldenbeanmall:import2]\n"
    "import io.github.aoguai.sesameag.task.exchange.ExchangeOptionsCache // [fork:goldenbeanmall:import3]\n"
)

HOLDER_ANCHOR = "    internal lateinit var goldenBeanManureExchangeDailyReserveAmount: IntegerModelField\n"
HOLDER_SNIPPET = (
    "    internal lateinit var goldenBeanMallExchange: BooleanModelField // [fork:goldenbeanmall:holder]\n"
    "    internal lateinit var goldenBeanMallExchangeList: SelectAndCountModelField // [fork:goldenbeanmall:holder2]\n"
)

FIELD_ANCHOR = "                ).also { goldenBeanManureExchangeDailyReserveAmount = it },\n        )\n"
FIELD_SNIPPET = """        modelFields.addField(
            BooleanModelField("goldenBeanMallExchange", "金豆商城 | 兑换", false)
                .withDesc(
                    "用金豆罐兑换下方所选商品规格；实付、外部下单或权益领取方式不明的商品只提醒不执行。",
                ).also { goldenBeanMallExchange = it }, // [fork:goldenbeanmall:field]
        )
        modelFields.addField(
            SelectAndCountModelField(
                "goldenBeanMallExchangeList",
                "金豆商城 | 商品规格与每日次数",
                LinkedHashMap<String?, Int?>(),
                { ExchangeOptionsCache.loadForSettingsCache(UserMap.currentUid, ExchangeOptionsRefreshBridge.TARGET_GOLDEN_BEAN_MALL) },
                "选择商品规格并设置每日兑换次数；0 表示不限，仍遵守服务端额度。开启并执行一次后返回设置页可刷新出商品列表。",
            ).also { goldenBeanMallExchangeList = it }, // [fork:goldenbeanmall:field2]
        )
"""

FLOW_ANCHOR = """    if (goldenBeanTreasure.value == true) {
        try {
            runGoldenBeanTreasure()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Log.printStackTrace("GoldenBeanTreasure", "run err:", e)
        }
    }
"""

FLOW_SNIPPET = """
    // [fork:goldenbeanmall:flow] 商城兑换独立于主开关，放在金豆任务之后单独处理
    if (goldenBeanMallExchange.value == true) {
        try {
            runGoldenBeanMallExchange()
        } catch (e: CancellationException) {
            throw e
        } catch (e: Exception) {
            Log.printStackTrace("GoldenBeanMall", "run err:", e)
        }
    }
"""

RPC_ANCHOR = "    fun listTopItemsByScene(): String ="
RPC_SNIPPET = """    // [fork:goldenbeanmall:rpc] 金豆商城：兑换下单与订单查询
    fun exchangeBenefit(spuId: String, skuId: String, requestId: String): String =
        request(
            "com.alipay.antcommonweal.exchange.h5.exchangeBenefit",
            JSONObject().apply {
                put("bizType", "MASTER")
                put("requestId", requestId)
                put("sceneCode", "ANTORCHARD_JINDOU_MALL")
                put("skuId", skuId)
                put("source", "MASTER")
                put("spuId", spuId)
                put("version", VERSION)
            },
        )

    fun queryExchangeOrders(
        pageNum: Int,
        size: Int = 20,
    ): String =
        request(
            "com.alipay.antcommonweal.exchange.h5.queryExchangeOrders",
            JSONObject().apply {
                put("bizType", "MASTER")
                put("pageNum", pageNum)
                put("sceneCode", "ANTORCHARD_JINDOU_MALL")
                put("size", size)
                put("source", "antorchard")
                put("version", VERSION)
            },
        )

"""

SUPPORT_ANCHOR = "private object GoldenBeanTreasureSupport {\n"
SUPPORT_SNIPPET = "// [fork:goldenbeanmall:support] 商城兑换复用同一套响应判定与失败归类\ninternal object GoldenBeanTreasureSupport {\n"

FLAG_ANCHOR = '    const val FLAG_ANTORCHARD_GOLDEN_BEAN_TASKS_DONE = "AntOrchard::goldenBeanTasksDone"\n'
FLAG_SNIPPET = """
    /** 金豆商城：兑换计数前缀，后接商品规格 id */
    const val FLAG_GOLDEN_BEAN_MALL_EXCHANGE_COUNT_PREFIX = "AntOrchard::goldenBeanMallExchangeCount::" // [fork:goldenbeanmall:flag]
"""

TARGET_ANCHOR = '    const val TARGET_SESAME_GRAIN = "sesame_grain"\n'
TARGET_SNIPPET = '    const val TARGET_GOLDEN_BEAN_MALL = "golden_bean_mall" // [fork:goldenbeanmall:target]\n'

DISPATCH_ANCHOR = """                    ExchangeOptionsRefreshBridge.TARGET_SESAME_GRAIN -> {
                        Model.getModel(AntSesameCredit::class.java)?.refreshSesameGrainExchangeOptionsForRemote()
                            ?: return ExchangeOptionsRefreshResult(false, "芝麻信用模块未初始化", currentUserId)
                    }
"""
DISPATCH_SNIPPET = """
                    ExchangeOptionsRefreshBridge.TARGET_GOLDEN_BEAN_MALL -> {
                        // [fork:goldenbeanmall:dispatch]
                        Model.getModel(AntOrchard::class.java)?.refreshGoldenBeanMallOptionsForRemote()
                            ?: return ExchangeOptionsRefreshResult(false, "芭芭农场模块未初始化", currentUserId)
                    }
"""

DISPATCH_IMPORT_ANCHOR = "import io.github.aoguai.sesameag.task.antMember.AntMember\n"
DISPATCH_IMPORT_SNIPPET = (
    "import io.github.aoguai.sesameag.task.antOrchard.AntOrchard // [fork:goldenbeanmall:dispatchimport]\n"
    "import io.github.aoguai.sesameag.task.antOrchard.refreshGoldenBeanMallOptionsForRemote "
    "// [fork:goldenbeanmall:dispatchimport2]\n"
)


def apply(patch):
    patch.add_file(ANTORCHARD + "GoldenBeanMall.kt", "tasks/GoldenBeanMall.kt")

    model = patch.edit(ANTORCHARD + "AntOrchard.kt")
    model.insert_after(IMPORT_ANCHOR, IMPORT_SNIPPET, "import1")
    model.insert_after(HOLDER_ANCHOR, HOLDER_SNIPPET, "holder")
    model.insert_after(FIELD_ANCHOR, FIELD_SNIPPET, "field")

    flow = patch.edit(ANTORCHARD + "AntOrchardWorkflow.kt")
    flow.insert_after(FLOW_ANCHOR, FLOW_SNIPPET, "flow")

    rpc = patch.edit(ANTORCHARD + "GoldenBeanRpcCall.kt")
    rpc.insert_before(RPC_ANCHOR, RPC_SNIPPET, "rpc")

    support = patch.edit(ANTORCHARD + "GoldenBeanTreasure.kt")
    support.replace(SUPPORT_ANCHOR, SUPPORT_SNIPPET, "support")

    flags = patch.edit(SRC + "data/StatusFlags.kt")
    flags.insert_after(FLAG_ANCHOR, FLAG_SNIPPET, "flag")

    bridge = patch.edit(SRC + "hook/ExchangeOptionsRefreshBridge.kt")
    bridge.insert_after(TARGET_ANCHOR, TARGET_SNIPPET, "target")

    dispatcher = patch.edit(SRC + "hook/ApplicationBroadcastDispatcher.kt")
    dispatcher.insert_after(DISPATCH_IMPORT_ANCHOR, DISPATCH_IMPORT_SNIPPET, "dispatchimport")
    dispatcher.insert_after(DISPATCH_ANCHOR, DISPATCH_SNIPPET, "dispatch")


if __name__ == "__main__":
    run(TAG, apply)
