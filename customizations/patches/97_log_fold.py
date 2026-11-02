#!/usr/bin/env python3
"""把「同一原因刷几百行」的提示折叠成一条。

现场一次运行 5701 行里，有 570 行在重复三件事：

- 持久调度未注册 376 行（禁止前台拉起时每个蹲点/子任务各一条）
- 蹲点降级 47 行 + 持久化同步 60 行（同一个动作两遍）
- 逐好友「正在查询主页」57 行（纯 trace）

根因只有一个：设置里开着「禁止系统调度前台拉起目标应用」。这类提示按原因折叠，
第一次详细记、之后每 N 次报一次累计数。逐好友 trace 下沉到「运行时日志」，
需要时在「日志 - 运行时」里仍然查得到。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "logfold"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"

LOG_IMPORT_ANCHOR = "import io.github.aoguai.sesameag.util.Log\n"


def import_snippet(name: str) -> str:
    return f"import io.github.aoguai.sesameag.util.LogFold // [fork:logfold:import{name}]\n"


# ---- 1. 持久调度注册表：每个 plan 一条 → 每 50 个汇总 ----
REGISTRY_ANCHOR = (
    '            Log.record(TAG, "持久调度已因禁止系统调度前台拉起目标应用而未注册[${effectiveSchedule.name}]")\n'
)
REGISTRY_SNIPPET = """            LogFold.tick("schedule_unregistered", 50)?.let { total ->
                Log.record(
                    TAG,
                    if (total == 1) {
                        "禁止系统调度前台拉起目标应用已开启，持久调度不会注册（同类提示每 50 个汇总一次）"
                    } else {
                        "持久调度仍未注册：累计 $total 个（禁止前台拉起）"
                    },
                )
            } // [fork:logfold:registry]
"""

# ---- 2. 四个模块的「持久子任务降级」：共用同一个计数 ----
FARM_ANCHOR = (
    '                Log.farm("庄园持久子任务[$group][$childId]已因禁止系统调度前台拉起目标应用降级为仅进程存活时等待，需手动打开目标应用后恢复")\n'
)
FARM_SNIPPET = """                LogFold.tick("schedule_downgraded", 20)?.let { total ->
                    Log.farm("庄园持久子任务[$group][$childId]已降级为仅进程存活时等待" + LogFold.foldedTail(total))
                } // [fork:logfold:farm]
"""

SPORTS_ANCHOR = (
    '                Log.sports("运动持久子任务[$group][$childId]已因禁止系统调度前台拉起目标应用降级为仅进程存活时等待，需手动打开目标应用后恢复")\n'
)
SPORTS_SNIPPET = """                LogFold.tick("schedule_downgraded", 20)?.let { total ->
                    Log.sports("运动持久子任务[$group][$childId]已降级为仅进程存活时等待" + LogFold.foldedTail(total))
                } // [fork:logfold:sports]
"""

STALL_ANCHOR = (
    '                Log.stall("新村持久子任务[$group][$childId]已因禁止系统调度前台拉起目标应用降级为仅进程存活时等待，需手动打开目标应用后恢复")\n'
)
STALL_SNIPPET = """                LogFold.tick("schedule_downgraded", 20)?.let { total ->
                    Log.stall("新村持久子任务[$group][$childId]已降级为仅进程存活时等待" + LogFold.foldedTail(total))
                } // [fork:logfold:stall]
"""

FOREST_ANCHOR = """                if (loggedFrontLaunchDisabledWaitingTasks.add(task.taskId)) {
                    Log.forest(
                        "森林蹲点持久任务[${task.taskId}][${task.getUserTypeTag()}${task.userName}]已因禁止系统调度前台拉起目标应用降级为仅进程存活时等待，需手动打开目标应用后恢复",
                    )
                }
"""
FOREST_SNIPPET = """                if (loggedFrontLaunchDisabledWaitingTasks.add(task.taskId)) {
                    LogFold.tick("schedule_downgraded", 20)?.let { total ->
                        Log.forest(
                            "森林蹲点持久任务[${task.taskId}][${task.getUserTypeTag()}${task.userName}]已降级为仅进程存活时等待" +
                                LogFold.foldedTail(total),
                        )
                    } // [fork:logfold:forest]
                }
"""

# ---- 3. 持久化同步：每加一个蹲点一条 → 每 20 条汇总 ----
SYNC_ANCHOR = '                        Log.forest("$statusText (uid: ${store.uid})")\n'
SYNC_SNIPPET = (
    '                        LogFold.tick("persist_sync", 20)?.let { Log.forest("$statusText (uid: ${store.uid})") }'
    " // [fork:logfold:sync]\n"
)

# ---- 4. 逐好友主页查询：森林频道 → 运行时日志 ----
QUERY_PK_ANCHOR = '            Log.forest("  正在查询PK好友 [$userName$userId] 的主页...")\n'
QUERY_PK_SNIPPET = '            Log.runtime(TAG, "正在查询PK好友 [$userName$userId] 的主页") // [fork:logfold:querypk]\n'

QUERY_FRIEND_ANCHOR = '            Log.forest("  正在查询好友 [$userName$userId] 的主页...")\n'
QUERY_FRIEND_SNIPPET = '            Log.runtime(TAG, "正在查询好友 [$userName$userId] 的主页") // [fork:logfold:queryfriend]\n'

# (相对路径, 导入标记名, 锚点, 片段, 片段名)；导入标记名 None 表示该文件已 import util.*
SITES = [
    ("task/antForest/EnergyWaitingManager.kt", "forest", FOREST_ANCHOR, FOREST_SNIPPET, "forest"),
    ("task/antFarm/AntFarm.kt", "farm", FARM_ANCHOR, FARM_SNIPPET, "farm"),
    ("task/antSports/AntSports.kt", None, SPORTS_ANCHOR, SPORTS_SNIPPET, "sports"),
    ("task/antStall/AntStall.kt", "stall", STALL_ANCHOR, STALL_SNIPPET, "stall"),
]


def apply(patch):
    patch.add_file(SRC + "util/LogFold.kt", "util/LogFold.kt")

    registry = patch.edit(SRC + "hook/keepalive/PersistentScheduleRegistry.kt")
    registry.insert_after(LOG_IMPORT_ANCHOR, import_snippet("registry"), "importregistry")
    registry.replace(REGISTRY_ANCHOR, REGISTRY_SNIPPET, "registry")

    for rel_path, import_name, anchor, snippet, name in SITES:
        editor = patch.edit(SRC + rel_path)
        if import_name is not None:
            editor.insert_after(LOG_IMPORT_ANCHOR, import_snippet(import_name), "import" + import_name)
        editor.replace(anchor, snippet, name)

    persistence = patch.edit(SRC + "task/antForest/EnergyWaitingPersistence.kt")
    persistence.insert_after(LOG_IMPORT_ANCHOR, import_snippet("persist"), "importpersist")
    persistence.replace(SYNC_ANCHOR, SYNC_SNIPPET, "sync")

    # 逐好友 trace 换成 Log.runtime；这两个文件本来就 import 了 Log
    forest = patch.edit(SRC + "task/antForest/AntForest.kt")
    forest.replace(QUERY_PK_ANCHOR, QUERY_PK_SNIPPET, "querypk")
    forest.replace(QUERY_FRIEND_ANCHOR, QUERY_FRIEND_SNIPPET, "queryfriend")


if __name__ == "__main__":
    run(TAG, apply)
