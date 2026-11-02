#!/usr/bin/env python3
"""把「内部数据直出」的日志改成能读的摘要。

现场日志里三处最刺眼：

1. 金豆商城探测：一件商品一行，还带一堆 ``itemStatus=UNKNOWN skuStatus=UNKNOWN``，
   一次探测就刷几十行；真正有用的只有「有几件能换、多少钱」。
2. 巡护事件奖励：整段服务端 JSON 原样塞进日志，里面还夹着 ``<\\/energy>`` 转义，
   肉眼根本看不出得了多少能量。
3. 配置格式化：``格式化配置: ***`` 是脱敏后的空壳，除了表示「又格式化了一次」没有任何信息。

三处都改成一句话摘要。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "logclean"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"

# ---- 1. 金豆商城：逐件明细 → 一条汇总 ----
MALL_ANCHOR = '''    private fun logMallItems(
        items: JSONArray,
        listType: String,
    ) {
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            val itemId =
                item.optString("spuId")
                    .ifBlank { item.optString("itemId") }
                    .ifBlank { item.optString("id") }
            val firstSku = item.optJSONArray("skuModelList")?.optJSONObject(0)
            val minPrice = item.optJSONObject("minPrice")
            Log.goldenBean(
                "金豆夺宝商城[${listType}只读] itemId=${itemId.ifBlank { "UNKNOWN" }} " +
                    "itemStatus=${item.optString("itemStatus").ifBlank { "UNKNOWN" }} " +
                    "skuId=${firstSku?.optString("skuId").orEmpty().ifBlank { "UNKNOWN" }} " +
                    "skuStatus=${firstSku?.optString("skuRuleResult").orEmpty().ifBlank { "UNKNOWN" }} " +
                    "stock=${item.optInt("remainStockCounts", -1)} " +
                    "priceCent=${minPrice?.optInt("cent", -1)}",
            )
        }
    }
'''

MALL_SNIPPET = '''    private fun logMallItems(
        items: JSONArray,
        listType: String,
    ) {
        // 一件商品一行、还带着一串 UNKNOWN，一次探测就能刷几十行；// [fork:logclean:mall]
        // 真正决定「换不换」的只有可兑换数量和价格，所以压成一条汇总。
        val available = mutableListOf<String>()
        for (index in 0 until items.length()) {
            val item = items.optJSONObject(index) ?: continue
            val firstSku = item.optJSONArray("skuModelList")?.optJSONObject(0)
            val itemOk = item.optString("itemStatus").equals("AVAILABLE", ignoreCase = true)
            val skuOk = firstSku?.optString("skuRuleResult").equals("AVAILABLE", ignoreCase = true)
            if (!itemOk && !skuOk) continue
            val itemId =
                item.optString("spuId")
                    .ifBlank { item.optString("itemId") }
                    .ifBlank { item.optString("id") }
            val cent = item.optJSONObject("minPrice")?.optInt("cent", -1) ?: -1
            val stock = item.optInt("remainStockCounts", -1)
            available += "${itemId.ifBlank { "?" }}(${cent}分/剩${stock})"
        }
        val summary =
            if (available.isEmpty()) {
                "金豆夺宝商城[$listType] 共 ${items.length()} 件，当前无可兑换商品"
            } else {
                "金豆夺宝商城[$listType] 共 ${items.length()} 件，可兑换 ${available.size} 件：" +
                    available.joinToString("、")
            }
        Log.goldenBean(summary)
    }
'''

# ---- 2. 配置格式化：脱敏空壳 → 字符数变化 ----
CONFIG_ANCHOR = '''                            Log.record(TAG, "格式化配置: $userName")
'''
CONFIG_SNIPPET = '''                            Log.record(TAG, "配置已重写: ${json.length} -> ${formatted.length} 字符") // [fork:logclean:config]
'''


def apply(patch):
    treasure = patch.edit(SRC + "task/antOrchard/GoldenBeanTreasure.kt")
    treasure.replace(MALL_ANCHOR, MALL_SNIPPET, "mall")

    config = patch.edit(SRC + "data/Config.kt")
    config.replace(CONFIG_ANCHOR, CONFIG_SNIPPET, "config")


if __name__ == "__main__":
    run(TAG, apply)
