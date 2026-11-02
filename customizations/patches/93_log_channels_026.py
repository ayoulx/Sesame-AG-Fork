#!/usr/bin/env python3
"""日志频道跟进 0.2.6：用「保护地巡护」「金豆夺宝」替掉「福气鱼池」。

0.1.9 的日志页面有「福气鱼池」这一项，0.2.6 把它拿掉了，换成两个更贴业务的
频道：

- 保护地巡护：新旧巡护、动物能量与派遣、保护证书；
- 金豆夺宝：签到、任务、金猫矿工、金豆乐园与商城兑换。

留着不分频道也能跑，但日志页会看到两件别扭事：
1) 巡护的轮次总结只要本轮有一个失败，就走 ``logError`` → ``Log.error(TAG)``
   落到错误频道，同一句话在其他轮次又出现在「森林」里；
2) 金豆夺宝的 24 条业务日志全挤在「农场」频道里，和施肥、果树分不开。

所以这里按 0.2.6 的频道表补上两个 domain + 两个 channel，并把调用点改过去。
福气鱼池那一项由 92 补丁删除，这里不再出现。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "logchan"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"

# ---- LogModuleDomain：补两个业务域 ----
DOMAIN_PATROL_ANCHOR = '    FOREST("蚂蚁森林"),\n'
DOMAIN_PATROL_SNIPPET = '    FOREST_PATROL("保护地巡护"), // [fork:logchan:domainpatrol]\n'

DOMAIN_GOLDEN_ANCHOR = '    ORCHARD("芭芭农场"),\n'
DOMAIN_GOLDEN_SNIPPET = '    GOLDEN_BEAN("金豆夺宝"), // [fork:logchan:domaingolden]\n'

# ---- LogChannel：补两个频道条目 ----
CHANNEL_PATROL_ANCHOR = """    FOREST(
        loggerName = "forest",
        displayName = "森林日志",
        moduleDomain = LogModuleDomain.FOREST,
        techKind = LogTechKind.BUSINESS,
        description = "蚂蚁森林与保护地相关业务日志",
        viewerGroup = LogViewerGroup.MODULES,
        mirrorToRecord = true,
        visibleInViewer = true,
        logTag = "森林"
    ),
"""
CHANNEL_PATROL_SNIPPET = """    FOREST_PATROL(
        loggerName = "forest_patrol",
        displayName = "保护地巡护日志",
        moduleDomain = LogModuleDomain.FOREST_PATROL,
        techKind = LogTechKind.BUSINESS,
        description = "新旧巡护、动物能量与派遣、保护证书日志",
        viewerGroup = LogViewerGroup.MODULES,
        mirrorToRecord = true,
        visibleInViewer = true,
        logTag = "保护地巡护"
    ), // [fork:logchan:channelpatrol]
"""

CHANNEL_GOLDEN_ANCHOR = """    ORCHARD(
        loggerName = "orchard",
        displayName = "农场日志",
        moduleDomain = LogModuleDomain.ORCHARD,
        techKind = LogTechKind.BUSINESS,
        description = "芭芭农场施肥、肥料与果树相关日志",
        viewerGroup = LogViewerGroup.MODULES,
        mirrorToRecord = true,
        visibleInViewer = true,
        logTag = "农场"
    ),
"""
CHANNEL_GOLDEN_SNIPPET = """    GOLDEN_BEAN(
        loggerName = "golden_bean",
        displayName = "金豆夺宝日志",
        moduleDomain = LogModuleDomain.GOLDEN_BEAN,
        techKind = LogTechKind.BUSINESS,
        description = "金豆夺宝签到、任务、金猫矿工、金豆乐园与肥料换豆日志",
        viewerGroup = LogViewerGroup.MODULES,
        mirrorToRecord = true,
        visibleInViewer = true,
        logTag = "金豆夺宝"
    ), // [fork:logchan:channelgolden]
"""

# ---- 来源类名别名：日志详情里显示「这条日志是哪个类打的」 ----
ALIAS_PATROL_ANCHOR = """        LogChannel.ORCHARD to setOf(
            "AntOrchard",
"""
ALIAS_PATROL_SNIPPET = """        LogChannel.FOREST_PATROL to setOf(
            "AntForestPatrol",
            "AntForestPatrolRpcCall",
            "LegacyPatrolWorkflow",
            "MonopolyPatrolWorkflow"
        ), // [fork:logchan:aliaspatrol]
"""

ALIAS_GOLDEN_ANCHOR = """        LogChannel.FARM to setOf(
            "AntFarm",
"""
ALIAS_GOLDEN_SNIPPET = """        LogChannel.GOLDEN_BEAN to setOf(
            "GoldenBeanTreasure",
            "GoldenBeanMall"
        ), // [fork:logchan:aliasgolden]
"""

# ---- Log 便捷方法 ----
FOREST_FUN_ANCHOR = """    fun forest(msg: String, type: Int = 1) {
        business(LogChannel.FOREST, msg, type)
    }
"""
FOREST_FUN_SNIPPET = """
    @JvmStatic
    fun forestPatrol(msg: String) {
        business(LogChannel.FOREST_PATROL, msg)
    }
    // [fork:logchan:funpatrol]
"""

ORCHARD_FUN_ANCHOR = """    fun orchard(msg: String) {
        business(LogChannel.ORCHARD, msg)
    }
"""
ORCHARD_FUN_SNIPPET = """
    @JvmStatic
    fun goldenBean(msg: String) {
        business(LogChannel.GOLDEN_BEAN, msg)
    }
    // [fork:logchan:fungolden]
"""

# ---- 日志页图标 ----
ICON_ANCHOR = """private fun iconFor(channel: LogChannel): ImageVector {
    return when (channel) {
"""
ICON_SNIPPET = """        LogChannel.FOREST_PATROL -> Icons.Rounded.Forest // [fork:logchan:icon]
        LogChannel.GOLDEN_BEAN -> Icons.Rounded.Agriculture
"""

# ---- 模块检查消息按任务名分流 ----
MODULE_LOG_ANCHOR = '            "蚂蚁森林", "蚂蚁森林合种", "保护地", "生态保护" -> Log.forest(msg)\n'
MODULE_LOG_SNIPPET = '            "保护地巡护" -> Log.forestPatrol(msg) // [fork:logchan:modulelog]\n'


def apply(patch):
    catalog = patch.edit(SRC + "util/LogCatalog.kt")
    catalog.insert_after(DOMAIN_PATROL_ANCHOR, DOMAIN_PATROL_SNIPPET, "domainpatrol")
    catalog.insert_after(DOMAIN_GOLDEN_ANCHOR, DOMAIN_GOLDEN_SNIPPET, "domaingolden")
    catalog.insert_after(CHANNEL_PATROL_ANCHOR, CHANNEL_PATROL_SNIPPET, "channelpatrol")
    catalog.insert_after(CHANNEL_GOLDEN_ANCHOR, CHANNEL_GOLDEN_SNIPPET, "channelgolden")
    catalog.insert_before(ALIAS_PATROL_ANCHOR, ALIAS_PATROL_SNIPPET, "aliaspatrol")
    catalog.insert_before(ALIAS_GOLDEN_ANCHOR, ALIAS_GOLDEN_SNIPPET, "aliasgolden")

    log = patch.edit(SRC + "util/Log.kt")
    log.insert_after(FOREST_FUN_ANCHOR, FOREST_FUN_SNIPPET, "funpatrol")
    log.insert_after(ORCHARD_FUN_ANCHOR, ORCHARD_FUN_SNIPPET, "fungolden")

    icons = patch.edit(SRC + "ui/screen/content/LogsContent.kt")
    icons.insert_after(ICON_ANCHOR, ICON_SNIPPET, "icon")

    task = patch.edit(SRC + "task/ModelTask.kt")
    task.insert_after(MODULE_LOG_ANCHOR, MODULE_LOG_SNIPPET, "modulelog")

    # 金豆夺宝的 19 处 Log.orchard 统一改名：同一文件里重复出现，
    # 逐一写锚点既啰嗦又容易漂，用整篇替换。
    treasure = patch.edit(SRC + "task/antOrchard/GoldenBeanTreasure.kt")
    treasure.replace_all("Log.orchard(", "Log.goldenBean(", "goldenlog")


if __name__ == "__main__":
    run(TAG, apply)
