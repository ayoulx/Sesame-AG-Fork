package io.github.aoguai.sesameag.task.antForest

import io.github.aoguai.sesameag.data.Status
import io.github.aoguai.sesameag.data.StatusFlags
import io.github.aoguai.sesameag.util.Log
import io.github.aoguai.sesameag.util.ResChecker
import org.json.JSONArray
import org.json.JSONObject

/**
 * 森林每日换装：每个部位从背包里挑一件可用装扮，穿戴后回主页确认生效。
 *
 * 只认「剩余次数 > 0 且未过期」的装扮；确认不到就不打今日标记，下次运行再试。
 */
internal object ForestDress {

    private const val TAG = "ForestDress"

    /** 查询名 → 主页装扮位 */
    private val POSITIONS =
        linkedMapOf(
            "treeMain" to "tree__main",
            "bgSkyCloud" to "bg__sky_cloud",
            "bgSky0" to "bg__sky_0",
            "bgGroundA" to "bg__ground_a",
            "bgGroundB" to "bg__ground_b",
            "bgGroundC" to "bg__ground_c",
        )

    fun run() {
        if (Status.hasFlagToday(StatusFlags.FLAG_ANTFOREST_DAILY_DRESS)) return
        try {
            val selected = pickDresses() ?: return
            if (selected.isEmpty()) return

            val response = unwrap(AntForestRpcCall.wearDress(JSONArray(selected.values.toList())))
            if (!ResChecker.checkRes(TAG, response)) return

            val home = unwrap(AntForestRpcCall.queryHomePage())
            if (!ResChecker.checkRes(TAG, home)) return

            val worn = wornPositions(home)
            if (selected.all { (position, type) -> worn[position] == type }) {
                Status.setFlagToday(StatusFlags.FLAG_ANTFOREST_DAILY_DRESS)
                Log.forest("森林每日换装完成，共 ${selected.size} 个部位")
            } else {
                Log.error(TAG, "穿戴已受理，主页尚未确认全部部位，下次再试")
            }
        } catch (t: Throwable) {
            if (t is kotlinx.coroutines.CancellationException || t is InterruptedException) throw t
            Log.printStackTrace(TAG, "每日换装失败", t)
        }
    }

    /** 逐个部位挑一件可用装扮；返回 null 表示本轮整体放弃。 */
    private fun pickDresses(): Map<String, String>? {
        val selected = linkedMapOf<String, String>()
        for ((query, position) in POSITIONS) {
            val data = unwrap(AntForestRpcCall.listUserDressForBackpack(query))
            if (!ResChecker.checkRes(TAG, data)) return null
            val owned = data.optJSONArray("userHoldDressVOList") ?: continue
            val option =
                (0 until owned.length())
                    .mapNotNull { owned.optJSONObject(it) }
                    .filter { dress -> dress.usableAt(position) }
                    .randomOrNull() ?: continue
            selected[position] = option.optString("dressType")
        }
        return selected
    }

    private fun JSONObject.usableAt(position: String): Boolean {
        if (optInt("remainNum") <= 0) return false
        if (optLong("expireTime") <= System.currentTimeMillis()) return false
        val type = optString("dressType")
        if (type.isBlank()) return false
        val slots = optJSONArray("posList") ?: return false
        return (0 until slots.length()).any { slots.optString(it) == position }
    }

    private fun wornPositions(home: JSONObject): Map<String, String> {
        val details = home.optJSONObject("indexDressVO")?.optJSONArray("dressDetailList") ?: return emptyMap()
        return (0 until details.length())
            .mapNotNull { details.optJSONObject(it) }
            .associate { it.optString("position") to it.optString("dressType") }
    }

    private fun unwrap(envelope: String): JSONObject {
        val json = JSONObject(envelope)
        return json.optJSONObject("resData") ?: json
    }
}
