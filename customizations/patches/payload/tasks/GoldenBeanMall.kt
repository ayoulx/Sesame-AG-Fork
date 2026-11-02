package io.github.aoguai.sesameag.task.antOrchard

import io.github.aoguai.sesameag.data.Status
import io.github.aoguai.sesameag.data.StatusFlags
import io.github.aoguai.sesameag.hook.ApplicationHookConstants
import io.github.aoguai.sesameag.hook.ExchangeOptionsRefreshBridge
import io.github.aoguai.sesameag.task.common.TaskFlowItem
import io.github.aoguai.sesameag.task.common.TaskRpcFailureType
import io.github.aoguai.sesameag.task.exchange.ExchangeCost
import io.github.aoguai.sesameag.task.exchange.ExchangeDisplayMeta
import io.github.aoguai.sesameag.task.exchange.ExchangeItem
import io.github.aoguai.sesameag.task.exchange.ExchangeLimit
import io.github.aoguai.sesameag.task.exchange.ExchangeOptionRow
import io.github.aoguai.sesameag.task.exchange.ExchangeOptionsCache
import io.github.aoguai.sesameag.task.exchange.ExchangeSafety
import io.github.aoguai.sesameag.util.CoroutineUtils
import io.github.aoguai.sesameag.util.Log
import io.github.aoguai.sesameag.util.RandomUtil
import io.github.aoguai.sesameag.util.TimeUtil
import io.github.aoguai.sesameag.util.UserDataStore
import io.github.aoguai.sesameag.util.UserDataStoreManager
import io.github.aoguai.sesameag.util.maps.UserMap
import kotlinx.coroutines.CancellationException
import org.json.JSONArray
import org.json.JSONObject
import java.math.BigDecimal
import java.util.UUID

private const val TAG = "GoldenBeanMall"
private const val PENDING_KEY = "goldenBeanMallPending"
private const val CONVERGENCE_LIMIT = 8
private const val MAX_PAGES = 20

/**
 * 金豆商城兑换。0.2.6 用 ExchangeOptionsCache.getOrFetch/readAndReplaceFromLive 做
 * 断点续抓，0.1.9 没有这套会话；这里按同样口径直接翻页，翻完一次性落缓存。
 */
internal fun AntOrchard.refreshGoldenBeanMallOptionsForRemote(): List<ExchangeOptionRow> {
    val rows = collectGoldenBeanMallRows()
    ExchangeOptionsCache.save(UserMap.currentUid, ExchangeOptionsRefreshBridge.TARGET_GOLDEN_BEAN_MALL, rows)
    return rows
}

private fun collectGoldenBeanMallRows(): List<ExchangeOptionRow> {
    val topResponse = GoldenBeanTreasureSupport.parseResponse(GoldenBeanRpcCall.listTopItemsByScene())
    if (topResponse == null || !GoldenBeanTreasureSupport.isSuccess(topResponse)) {
        Log.error(TAG, "金豆商城运营位查询失败 raw=${topResponse ?: "EMPTY"}")
    }

    val rows = linkedMapOf<String, ExchangeOptionRow>()
    var startIndex = 0
    var page = 0
    while (page < MAX_PAGES) {
        val response = GoldenBeanTreasureSupport.parseResponse(GoldenBeanRpcCall.itemList(startIndex))
            ?: error("金豆商城商品列表返回空 startIndex=$startIndex")
        check(GoldenBeanTreasureSupport.isSuccess(response)) { "金豆商城列表查询失败 startIndex=$startIndex raw=$response" }
        val items = response.getJSONArray("itemInfoVOList")
        var added = 0
        for (i in 0 until items.length()) {
            val spu = items.getJSONObject(i)
            val spuId = spu.getString("spuId")
            require(spuId.isNotBlank()) { "金豆商城商品缺少 spuId" }
            val skus = spu.optJSONArray("skuModelList") ?: JSONArray()
            for (j in 0 until skus.length()) {
                val sku = skus.getJSONObject(j)
                require(sku.optString("skuId").isNotBlank()) { "金豆商城规格缺少 skuId:$sku" }
                val item = mallExchangeItem(spu, sku)
                if (rows.put(item.id, item.toOptionRow()) == null) added++
            }
        }
        val hasMore = response.optBoolean("hasMore", false)
        val next = if (hasMore) response.optInt("nextStartIndex", startIndex) else startIndex
        check(!hasMore || (items.length() > 0 && next > startIndex)) {
            "金豆商城分页未推进 startIndex=$startIndex next=$next"
        }
        check(items.length() == 0 || added > 0) { "金豆商城返回重复页 startIndex=$startIndex" }
        if (!hasMore) return rows.values.toList()
        startIndex = next
        page++
        CoroutineUtils.sleepCompat(RandomUtil.nextLong(300, 601))
    }
    Log.error(TAG, "金豆商城翻页超过上限，仅使用已取到的${rows.size}个规格")
    return rows.values.toList()
}

/**
 * 单个商品规格的兑换可行性。实付、外部下单、权益领取方式不明一律只提醒不执行，
 * 与服务端额度用尽一起构成「本轮不兑换」的判定。
 */
private fun mallExchangeItem(spu: JSONObject, sku: JSONObject): ExchangeItem {
    val cost = sku.optJSONObject("price")?.optLong("cent", -1L) ?: -1L
    val money = sku.optJSONObject("moneyPrice")
    val cash = if (!sku.has("moneyPrice") || sku.isNull("moneyPrice")) 0L else money?.optLong("cent", -1L) ?: -1L
    val externalOrder = spu.optString("outSpuType").isNotBlank() || spu.optString("outSpuId").isNotBlank() ||
        sku.optString("outSpuOrderLink").isNotBlank() || sku.optString("outSkuId").isNotBlank()
    val dayLeft = sku.optInt("userDayLeftAmount", -1)
    val totalLeft = sku.optInt("userTotalLeftAmount", -1)
    val stock = spu.optInt("remainStockCounts", -1)
    val (safety, reason) =
        when {
            cost < 0L -> ExchangeSafety.UNAVAILABLE to "未取得有效金豆罐价格"
            cash < 0L -> ExchangeSafety.LOG_ONLY to "实付金额未明确"
            cash > 0L || externalOrder -> ExchangeSafety.LOG_ONLY to "需要实付或外部下单"
            sku.optString("rightsConfigId").isBlank() -> ExchangeSafety.LOG_ONLY to "未明确内部权益领取方式"
            dayLeft == 0 || totalLeft == 0 || stock == 0 -> ExchangeSafety.UNAVAILABLE to "库存或兑换次数已用完"
            else -> ExchangeSafety.AUTO to ""
        }
    val name =
        listOf(spu.optString("spuName"), sku.optString("skuName"))
            .filter { it.isNotBlank() }.distinct().joinToString(" / ")
    return ExchangeItem(
        id = "${spu.optString("spuId")}:${sku.optString("skuId")}",
        name = name,
        cost =
        ExchangeCost(
            pointText =
            if (cost >= 0L) {
                "${BigDecimal.valueOf(cost, 2).stripTrailingZeros().toPlainString()}金豆罐"
            } else {
                "金豆罐价格未知"
            },
            cashText = if (cash > 0L) "${BigDecimal.valueOf(cash, 2).toPlainString()}${money?.optString("currencyCode", "CNY")}" else "",
        ),
        limit =
        ExchangeLimit(
            statusText = sku.optString("skuRuleResult"),
            stockText =
            listOfNotNull(
                stock.takeIf { it >= 0 }?.let { "库存$it" },
                dayLeft.takeIf { it >= 0 }?.let { "今日余${it}次" },
            ).joinToString("，"),
        ),
        safety = safety,
        safetyReason = reason,
        displayMeta = ExchangeDisplayMeta(sourceModule = "金豆罐"),
    )
}

internal fun AntOrchard.runGoldenBeanMallExchange() {
    val userId = UserMap.currentUid?.trim().orEmpty()
    if (userId.isBlank()) return
    val store = UserDataStoreManager.getInstance(userId) ?: return
    val startedAt = System.currentTimeMillis()

    fun checkCurrent() {
        check(UserMap.currentUid == store.uid) { "金豆商城账号已切换" }
        check(!ApplicationHookConstants.isOffline()) { "金豆商城本轮离线" }
        check(TimeUtil.isSameDay(startedAt, System.currentTimeMillis())) { "金豆商城本轮已跨天" }
    }

    try {
        val saved = store.get(PENDING_KEY, String::class.java)
        val pending = saved?.takeIf { it.isNotBlank() }?.let(::JSONObject) ?: JSONObject()
        if (pending.length() > 0 && !confirmMallExchange(store, pending, ::checkCurrent)) return
        if (goldenBeanMallExchange.value != true) return

        refreshGoldenBeanMallOptionsForRemote()
        val selected = goldenBeanMallExchangeList.value?.toMap().orEmpty()
        if (selected.isEmpty()) {
            Log.orchard("金豆商城未选择商品，仅更新兑换候选")
            return
        }
        var confirmed = 0
        for ((selectedId, configuredCount) in selected) {
            if (selectedId.isNullOrBlank() || configuredCount == null || configuredCount < 0) continue
            val countFlag = StatusFlags.FLAG_GOLDEN_BEAN_MALL_EXCHANGE_COUNT_PREFIX + selectedId
            while (confirmed < CONVERGENCE_LIMIT) {
                checkCurrent()
                val done = Status.getIntFlagToday(countFlag) ?: 0
                if (configuredCount > 0 && done >= configuredCount) break
                val match = findMallProduct(selectedId)
                if (match == null) {
                    Log.error(TAG, "金豆商城所选规格已不在当前目录:$selectedId")
                    break
                }
                val (spu, sku) = match
                val item = mallExchangeItem(spu, sku)
                if (item.safety != ExchangeSafety.AUTO) {
                    Log.orchard("金豆商城[${item.name}]本轮不兑换：${item.safetyReason}")
                    break
                }
                val index = GoldenBeanTreasureSupport.parseResponse(GoldenBeanRpcCall.index())
                    ?: error("金豆商城余额查询返回空")
                check(GoldenBeanTreasureSupport.isSuccess(index)) { "金豆商城余额查询失败:$index" }
                val balance = index.optJSONObject("jarInfo")?.optString("jarCount")?.toBigDecimalOrNull()
                    ?: error("金豆商城未取得有效金豆罐余额")
                val cost = BigDecimal.valueOf(sku.getJSONObject("price").getLong("cent"), 2)
                check(balance.signum() >= 0) { "金豆罐余额无效:$balance" }
                if (balance < cost) {
                    Log.orchard("金豆商城[${item.name}]金豆罐不足，余额$balance，需$cost")
                    break
                }

                val beforeOrders = queryMallOrderNos(::checkCurrent)
                val request =
                    JSONObject()
                        .put("itemId", selectedId).put("spuId", spu.getString("spuId"))
                        .put("skuId", sku.getString("skuId"))
                        .put("name", item.name).put("requestId", UUID.randomUUID().toString())
                        .put("requestedAt", System.currentTimeMillis())
                        .put("beforeOrderNos", JSONArray(beforeOrders))
                checkCurrent()
                store.put(PENDING_KEY, request.toString())
                checkCurrent()
                val response =
                    GoldenBeanTreasureSupport.parseResponse(
                        GoldenBeanRpcCall.exchangeBenefit(
                            request.getString("spuId"),
                            request.getString("skuId"),
                            request.getString("requestId"),
                        ),
                    )
                checkCurrent()
                if (response == null) {
                    Log.error(TAG, "金豆商城兑换响应为空，保留待确认:$selectedId")
                    return
                }
                val acknowledged = GoldenBeanTreasureSupport.isSuccess(response)
                val failure =
                    if (acknowledged) {
                        null
                    } else {
                        GoldenBeanTreasureSupport.actionResult(
                            TaskFlowItem(
                                selectedId,
                                item.name,
                                "TODO",
                                type = sku.getString("skuId"),
                                sceneCode = "ANTORCHARD_JINDOU_MALL",
                            ),
                            response,
                            "exchangeBenefit",
                        )
                    }
                if (response.opt("canBuy") == false ||
                    failure?.failureType in
                    setOf(TaskRpcFailureType.NON_RETRYABLE_INVALID, TaskRpcFailureType.UNSUPPORTED_NO_CLOSURE)
                ) {
                    Log.error(TAG, "金豆商城未受理兑换[${item.name}]:$response")
                    store.put(PENDING_KEY, "{}")
                    break
                }
                request.put("acknowledged", acknowledged).put("orderNo", response.optString("orderNo"))
                store.put(PENDING_KEY, request.toString())
                if (!acknowledged) Log.error(TAG, "金豆商城兑换未确认成功，保留订单回查:$response")
                if (!confirmMallExchange(store, request, ::checkCurrent)) return
                confirmed++
                // 保留金豆 executeInterval 配置的连续兑换间隔，并沿用原有 425–500ms 随机下限。
                CoroutineUtils.sleepCompat(executeIntervalInt.toLong().coerceAtLeast(RandomUtil.nextLong(425, 501)))
            }
            if (confirmed >= CONVERGENCE_LIMIT) {
                Log.orchard("金豆商城本轮已确认${confirmed}笔，剩余配置留待后续调度")
                return
            }
        }
    } catch (e: CancellationException) {
        throw e
    } catch (e: InterruptedException) {
        throw e
    } catch (e: Throwable) {
        Log.printStackTrace(TAG, "金豆商城兑换失败:", e)
    }
}

private fun findMallProduct(selectedId: String): Pair<JSONObject, JSONObject>? {
    val spuId = selectedId.substringBefore(":")
    val skuId = selectedId.substringAfter(":")
    var startIndex = 0
    var page = 0
    while (page < MAX_PAGES) {
        val response = GoldenBeanTreasureSupport.parseResponse(GoldenBeanRpcCall.itemList(startIndex))
            ?: return null
        if (!GoldenBeanTreasureSupport.isSuccess(response)) return null
        val items = response.getJSONArray("itemInfoVOList")
        for (i in 0 until items.length()) {
            val spu = items.getJSONObject(i)
            if (spu.optString("spuId") != spuId) continue
            val skus = spu.optJSONArray("skuModelList") ?: JSONArray()
            for (j in 0 until skus.length()) {
                val sku = skus.getJSONObject(j)
                if (sku.optString("skuId") == skuId) return spu to sku
            }
        }
        val hasMore = response.optBoolean("hasMore", false)
        val next = if (hasMore) response.optInt("nextStartIndex", startIndex) else startIndex
        if (!hasMore || next <= startIndex) return null
        startIndex = next
        page++
    }
    return null
}

private fun queryMallOrderNos(checkCurrent: () -> Unit): List<String> {
    val orders = linkedMapOf<String, JSONObject>()
    var page = 1
    while (page <= MAX_PAGES) {
        checkCurrent()
        val response = GoldenBeanTreasureSupport.parseResponse(GoldenBeanRpcCall.queryExchangeOrders(page))
            ?: error("金豆商城订单查询返回空")
        checkCurrent()
        check(GoldenBeanTreasureSupport.isSuccess(response)) { "金豆商城订单查询失败 page=$page raw=$response" }
        val list = response.getJSONArray("orderInfos")
        var added = 0
        for (i in 0 until list.length()) {
            val order = list.getJSONObject(i)
            val no = order.optString("orderNo")
            require(no.isNotBlank()) { "金豆商城订单缺少 orderNo:$order" }
            if (orders.put(no, order) == null) added++
        }
        check(list.length() == 0 || added > 0) { "金豆商城订单分页未推进 page=$page" }
        if (list.length() < 20) return orders.keys.toList()
        page++
        CoroutineUtils.sleepCompat(RandomUtil.nextLong(300, 601))
    }
    return orders.keys.toList()
}

/**
 * 兑换结果确认：订单列表里必须出现「提交后新增的、且提交前不存在的」同一个 orderNo，
 * 才认为这一笔真的成立，否则保留待确认状态、不重复提交。
 */
private fun confirmMallExchange(store: UserDataStore, pending: JSONObject, checkCurrent: () -> Unit): Boolean {
    checkCurrent()
    val itemId = pending.getString("itemId")
    val orderNo = pending.optString("orderNo")
    if (!pending.has("confirmedAt")) {
        val orders = queryMallOrderNos(checkCurrent)
        checkCurrent()
        val before = pending.getJSONArray("beforeOrderNos")
        val existed = (0 until before.length()).any { before.optString(it) == orderNo }
        if (!pending.optBoolean("acknowledged") || orderNo.isBlank() || existed || !orders.contains(orderNo)) {
            Log.error(
                TAG,
                "金豆商城待确认[${pending.optString("name")}] requestId=${pending.optString("requestId")} " +
                    "orderNo=$orderNo，未确认对应新增订单，不重复提交",
            )
            return false
        }
        pending.put("confirmedAt", System.currentTimeMillis())
        pending.put(
            "confirmedCount",
            (Status.getIntFlagToday(StatusFlags.FLAG_GOLDEN_BEAN_MALL_EXCHANGE_COUNT_PREFIX + itemId) ?: 0) + 1,
        )
        store.put(PENDING_KEY, pending.toString())
    }
    checkCurrent()
    if (TimeUtil.isSameDay(pending.getLong("confirmedAt"), System.currentTimeMillis())) {
        val flag = StatusFlags.FLAG_GOLDEN_BEAN_MALL_EXCHANGE_COUNT_PREFIX + itemId
        val expected = pending.getInt("confirmedCount")
        if ((Status.getIntFlagToday(flag) ?: 0) < expected) Status.setIntFlagToday(flag, expected)
        Log.orchard("金豆商城[${pending.optString("name")}]兑换确认成功 orderNo=$orderNo")
    }
    store.put(PENDING_KEY, "{}")
    return true
}
