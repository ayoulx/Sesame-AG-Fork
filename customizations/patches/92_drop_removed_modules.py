#!/usr/bin/env python3
"""删除上游 0.2.6 已移除的模块：福气鱼池、其他任务（信用2101）。

0.2.6 把这两块整体删掉了。留着它们会变成永远没人调用的死代码：任务不进
注册表、分组没有入口、日志频道没有来源，但状态标记、默认黑名单、RPC 抓包
仍在持续消费内存和启动时间。所以这里按上游的做法一并删干净。

删除清单：
- task/antFishPond/（AntFishPond、AntFishPondRpcCall）
- task/other/（OtherTask、credit2101/Credit2101、credit2101/Credit2101RpcCall）
- 引用层：模型分组/顺序、日志频道与分类、状态标记、默认黑名单、
  VIP riskToken 抓包、模块统计与「今日状态」解析。

删除没法在文件里留 [fork:tag:name] 标记（留了就不叫删干净了），幂等改由
patchkit 的 .state/dropped-<tag>.txt 记录；remove_file 以「文件已不存在」为已应用。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "drop92"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"

REMOVED_FILES = [
    SRC + "task/antFishPond/AntFishPond.kt",
    SRC + "task/antFishPond/AntFishPondRpcCall.kt",
    SRC + "task/other/OtherTask.kt",
    SRC + "task/other/credit2101/Credit2101.kt",
    SRC + "task/other/credit2101/Credit2101RpcCall.kt",
]

# 待删片段：(文件, 片段名, 原文)。原文是从基线文件里逐字节切出来的，不手抄，
# 缩进与空行保持原样——锚点要求全文恰好命中 1 次，多一个空格就会失配。
DROPS = [
    ("data/StatusFlags.kt", "fishflags", """\
    /** 福气鱼池：今日签到已处理 */
    const val FLAG_ANTFISHPOND_SIGN_DONE = "AntFishPond::signDone"

    /** 福气鱼池：每日宝箱已领取 */
    const val FLAG_ANTFISHPOND_GIFT_BOX_DONE = "AntFishPond::giftBoxDone"

    /** 福气鱼池：明日钓竿奖励已领取 */
    const val FLAG_ANTFISHPOND_TOMORROW_ROD_DONE = "AntFishPond::tomorrowRodDone"

    /** 福气鱼池：今日稳定任务已无可执行项 */
    const val FLAG_ANTFISHPOND_TASKS_DONE = "AntFishPond::tasksDone"

    /** 福气鱼池：缺少 fishpondAngle riskToken */
    const val FLAG_ANTFISHPOND_RISK_TOKEN_MISSING = "AntFishPond::riskTokenMissing"

    /** 福气鱼池：今日自动钓鱼次数 */
    const val FLAG_ANTFISHPOND_FISH_COUNT = "AntFishPond::fishCount"

    /** 福气鱼池：今日自动钓鱼达到配置上限 */
    const val FLAG_ANTFISHPOND_FISH_LIMIT_REACHED = "AntFishPond::fishLimitReached"

"""),
    ("data/StatusFlags.kt", "creditflags", """\
    /** 信用 2101：图鉴章节任务是否全部完成 */
    const val FLAG_CREDIT2101_CHAPTER_TASK_DONE: String = "FLAG_Credit2101_ChapterTask_Done"

    /** 信用 2101：事件当日计数前缀 */
    const val FLAG_CREDIT2101_EVENT_COUNT_PREFIX: String = "2101_Event_"

    /** 信用 2101：事件当日计数后缀 */
    const val FLAG_CREDIT2101_EVENT_COUNT_SUFFIX: String = "_COUNT_TODAY"

"""),
    ("hook/TokenHooker.kt", "fishrpc", """\
        registerRpcHandler("com.alipay.antfishpond.fishpondAngle") { paramsJson ->
            handleFishPondRiskToken(currentUserId, paramsJson)
        }

"""),
    ("hook/TokenHooker.kt", "fishhandler", """\
    private fun handleFishPondRiskToken(userId: String, paramsJson: JSONObject) {
        try {
            val requestData = extractFirstRequestData(paramsJson) ?: paramsJson
            val riskToken = requestData.optString("riskToken").orEmpty()
            if (riskToken.isBlank()) return

            val vipData = IdMapManager.getInstance(VipDataIdMap::class.java)
            vipData.load(userId)
            if (vipData[FISHPOND_RISK_TOKEN_KEY] == riskToken) {
                return
            }
            vipData.add(FISHPOND_RISK_TOKEN_KEY, riskToken)

            if (vipData.save(userId)) {
                Log.fishpond("捕获到福气鱼池 fishpondAngle riskToken 并已保存, uid=$userId")
            } else {
                Log.error(TAG, "保存福气鱼池 riskToken 到 vipdata.json 失败, uid=$userId")
            }
        } catch (e: Exception) {
            Log.error(TAG, "解析福气鱼池 riskToken 异常: ${e.message}")
        }
    }

"""),
    ("hook/TokenHooker.kt", "fishkey", """\

    private const val FISHPOND_RISK_TOKEN_KEY = "antfishpond_riskToken"
"""),
    ("model/CustomSettings.kt", "fishentity", """\
            SimpleEntity("antFishPond", "福气鱼池"),
"""),
    ("model/CustomSettings.kt", "fishtaskinfo", """\
            taskInfo.contains("福气鱼池") || taskInfo.contains("antFishPond") -> "antFishPond"
"""),
    ("model/CustomSettings.kt", "otherentity", """\
            SimpleEntity("other", "其他任务")
"""),
    ("model/CustomSettings.kt", "othertaskinfo", """\
            taskInfo.contains("其他任务") || taskInfo.contains("other") -> "other"
"""),
    ("model/ModelGroup.kt", "fishgroup", """\
    /** 福气鱼池 */
    FISHPOND("FISHPOND", "福气鱼池", "svg/group/orchard.svg"),
"""),
    ("model/ModelOrder.kt", "fishimport", """\
import io.github.aoguai.sesameag.task.antFishPond.AntFishPond
"""),
    ("model/ModelOrder.kt", "otherimport", """\
import io.github.aoguai.sesameag.task.other.OtherTask
"""),
    ("model/ModelOrder.kt", "fishorder", """\
        AntFishPond::class.java,   // 福气鱼池
"""),
    ("model/ModelOrder.kt", "otherorder", """\
        OtherTask::class.java,      // 其他
"""),
    ("task/ModelTask.kt", "fishlog", """\
            "福气鱼池" -> Log.fishpond(msg)
"""),
    ("task/ModelTask.kt", "fishgrouplog", """\
                ModelGroup.FISHPOND -> Log.fishpond(msg)
"""),
    ("task/TaskRunner.kt", "fishrunnerimport", """\
import io.github.aoguai.sesameag.task.antFishPond.AntFishPond
"""),
    ("task/TaskRunner.kt", "fishbatch", """\
            // 6) 福气鱼池放在农场之后，保持独立玩法批次。
            takeBatch { it is AntFishPond }
                .takeIf { it.isNotEmpty() }
                ?.let(::add)

"""),
    ("ui/dto/ModelFieldTodayStateResolver.kt", "fishfieldstate", """\
            "AntFishPond.fishPondTask" -> {
                allFlags(
                    StatusFlags.FLAG_ANTFISHPOND_SIGN_DONE,
                    StatusFlags.FLAG_ANTFISHPOND_GIFT_BOX_DONE,
                    StatusFlags.FLAG_ANTFISHPOND_TOMORROW_ROD_DONE,
                    StatusFlags.FLAG_ANTFISHPOND_TASKS_DONE,
                    reason = "今日鱼池任务奖励已处理",
                )
            }

"""),
    ("ui/dto/ModelFieldTodayStateResolver.kt", "fishautofish", """\
            "AntFishPond.autoFish",
            "AntFishPond.fishDailyLimit",
            -> {
                fishPondAutoFishState(modelFields)
            }

"""),
    ("ui/dto/ModelFieldTodayStateResolver.kt", "creditfieldstate", """\
            "OtherTask.credit2101",
            "OtherTask.CreditOptions",
            -> {
                credit2101OptionsState(modelFields["CreditOptions"] ?: modelField)
            }

"""),
    ("ui/dto/ModelFieldTodayStateResolver.kt", "fishfunc", """\
    private fun fishPondAutoFishState(modelFields: ModelFields): ModelFieldTodayState =
        when {
            Status.hasFlagToday(StatusFlags.FLAG_ANTFISHPOND_RISK_TOKEN_MISSING) -> {
                inactive("缺少 fishpondAngle riskToken，今日已跳过自动钓鱼")
            }

            else -> {
                limitReached(
                    current = Status.getIntFlagToday(StatusFlags.FLAG_ANTFISHPOND_FISH_COUNT),
                    limit = intValue(modelFields["fishDailyLimit"]),
                    reason = "今日自动钓鱼已达每日上限",
                )
            }
        }

"""),
    ("ui/dto/ModelFieldTodayStateResolver.kt", "creditfunc", """\
    private fun credit2101OptionsState(modelField: ModelField<*>): ModelFieldTodayState {
        val configuredCounts =
            countMapValue(modelField)
                .filterValues { it != 0 }
        if (configuredCounts.isEmpty()) {
            return ModelFieldTodayState()
        }
        if (configuredCounts.values.any { it < 0 }) {
            return ModelFieldTodayState()
        }

        return if (configuredCounts.all { (eventType, limit) ->
                (Status.getIntFlagToday(buildCredit2101EventCountFlag(eventType)) ?: 0) >= limit
            }
        ) {
            inactive("今日信用2101事件已达设定次数")
        } else {
            ModelFieldTodayState()
        }
    }

    private fun buildCredit2101EventCountFlag(eventType: String): String =
        StatusFlags.FLAG_CREDIT2101_EVENT_COUNT_PREFIX +
            eventType +
            StatusFlags.FLAG_CREDIT2101_EVENT_COUNT_SUFFIX

"""),
    ("util/Log.kt", "fishlogfun", """\
    @JvmStatic
    fun fishpond(msg: String) {
        business(LogChannel.FISHPOND, msg)
    }

"""),
    ("util/LogCatalog.kt", "fishdomain", """\
    FISHPOND("福气鱼池"),
"""),
    ("util/LogCatalog.kt", "fishchannel", """\
    FISHPOND(
        loggerName = "fishpond",
        displayName = "福气鱼池日志",
        moduleDomain = LogModuleDomain.FISHPOND,
        techKind = LogTechKind.BUSINESS,
        description = "福气鱼池钓竿、任务、钓鱼与兑换进度相关日志",
        viewerGroup = LogViewerGroup.MODULES,
        mirrorToRecord = true,
        visibleInViewer = true,
        logTag = "福气鱼池"
    ),
"""),
    ("util/LogCatalog.kt", "fishchannelmap", """\
        LogChannel.FISHPOND to setOf(
            "AntFishPond"
        ),
"""),
    ("util/defaultBlacklist.kt", "fishblacklist", """\
private val fishPondDefaultBlacklist =
    setOf(
        // 福气鱼池：游戏、订阅、分享、翻倍广告等任务缺少稳定自动完成闭环
        "FISHPOND_NCLY_GAME",
        "NORMAL_RENMENYOUXI",
        "TASK_SUBSCRIBE",
        "ANTFISHPOND_WECHAT_SHARE",
        "LOTTERY_PLUS",
        "RESCUE_AD",
        "RESULT_DOUBLE_AD",
        "FLOAT_GAME_AD",
        "玩保卫向日葵30s",
        "玩三国冰河时代30s",
        "农场对对碰匹配5组",
        "闯关挪挪车通过1关",
        "美食奇遇记合成10次",
        "农场螺丝王消除5组螺丝",
        "开启领钓竿提醒",
        "去玩热门小游戏",
        "送福袋 我也得福袋",
        "钓鱼结果页翻倍",
        "补救广告",
        "浮球游戏广告",
    )

"""),
    ("util/defaultBlacklist.kt", "fishblacklistmap", """\
        "福气鱼池" to fishPondDefaultBlacklist,
"""),
    ("entity/OtherEntity.kt", "creditimport", """\
import io.github.aoguai.sesameag.task.other.credit2101.Credit2101

"""),
    ("entity/OtherEntity.kt", "creditoptions", """\
    @JvmStatic
    fun listPropGroupOptions(): List<OtherEntity> = listOf(
        OtherEntity("COLLECT_HISTORY_ANIMAL_7_DAYS", "当前图鉴抽卡券 🎴"),
        OtherEntity("COLLECT_TO_FRIEND_TIMES_7_DAYS", "好友卡抽卡券 👥"),
        OtherEntity("COLLECT_TIMES_7_DAYS", "万能卡 🃏")
    )


    //信用2101任务列表
    @JvmStatic
    fun listCreditOptions(): List<OtherEntity> = listOf(
        OtherEntity(Credit2101.EventType.MINI_GAME_ELIMINATE, "消除小游戏 🎮"),
        OtherEntity(Credit2101.EventType.MINI_GAME_COLLECTYJ, "收集小游戏 🏺"),
        OtherEntity(Credit2101.EventType.MINI_GAME_MATCH3, "击杀小游戏 🧩"),
        OtherEntity(Credit2101.EventType.GOLD_MARK, "金色印记 🟡"),
        OtherEntity(Credit2101.EventType.BLACK_MARK, "黑色印记 ⚫"),
        OtherEntity(Credit2101.EventType.SPACE_TIME_GATE, "时空之门 🌀")
    )

"""),
]

# 需要改写的行（删除后顺带收拾：图标映射、批次编号、注释示例）。
REWRITES = [
    (
        "ui/screen/content/LogsContent.kt",
        "logicon",
        "        LogChannel.ORCHARD, LogChannel.FISHPOND, LogChannel.FARM, LogChannel.STALL -> Icons.Rounded.Agriculture\n",
        "        LogChannel.ORCHARD, LogChannel.FARM, LogChannel.STALL -> Icons.Rounded.Agriculture // [fork:drop92:logicon]\n",
    ),
    (
        "task/TaskRunner.kt",
        "renumberfarm",
        "            // 7) 庄园尽量承接前面模块已完成的联动任务状态，减少碎片奖励漏领。\n",
        "            // 6) 庄园尽量承接前面模块已完成的联动任务状态，减少碎片奖励漏领。 // [fork:drop92:renumberfarm]\n",
    ),
    (
        "task/TaskRunner.kt",
        "renumbermember",
        "            // 8) 会员与芝麻信用放在联动行为之后。\n",
        "            // 7) 会员与芝麻信用放在联动行为之后。 // [fork:drop92:renumbermember]\n",
    ),
    (
        "util/maps/VipDataIdMap.kt",
        "vipkey",
        ' *   "antfishpond_riskToken": "xxxx"\n',
        ' *   "AntFarmReferToken": "xxxx" // [fork:drop92:vipkey]\n',
    ),
]


def apply(patch):
    for path in REMOVED_FILES:
        patch.remove_file(path)

    for path, name, text in DROPS:
        patch.edit(SRC + path).drop(text, name)

    for path, name, old, new in REWRITES:
        patch.edit(SRC + path).replace(old, new, name)


if __name__ == "__main__":
    run(TAG, apply)
