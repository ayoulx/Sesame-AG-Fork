#!/usr/bin/env python3
"""好友关系自愈 + 跳过日志聚合。

两个问题都出在实测日志里：

1) 好友中心显示「全部失效好友」，收能量时 78 个好友被整批跳过，日志里
   ``好友收能量 跳过[...]：单向好友或已失效(relation=REMOVED)`` 出现 156 次。
   根因是剪枝把「本次快照里没出现」当成了「已删除好友」（由 91 补丁收口），
   但关系一旦被标成 REMOVED 并落盘，只靠每日一次的同步才能恢复；而每日同步
   又会因为「今日已刷新」直接跳过，于是中毒状态能持续一整天。
   这里在跳过分之前补一次「只增不减」的关系刷新：用当前好友快照重算关系，
   不做任何剪枝，把误标失效的人拉回来。

2) 逐条记录跳过日志把整份日志冲掉（156 行占 5%）。改成按场景开 60 秒窗口：
   窗口内第一条立即记录并附上同期数量，其余只计数。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "friendheal"
SRC = "app/src/main/java/io/github/aoguai/sesameag/"

# ---- 1. FriendRepository：只刷新关系、不剪枝 ----
REPO_ANCHOR = """        pruneGroups(config)
        save(safeUserId, config)
        Log.runtime(TAG, "好友中心刷新完成: profiles=${config.profiles.size}, groups=${config.groups.size}")
        return config
    }
"""
REPO_SNIPPET = '''
    /**
     * 用当前好友快照重算关系，但绝不剪枝。
     *
     * 只做两件事：把快照里出现的人补进好友中心、按最新 friendStatus 重算关系。
     * 快照里没出现的人一律保持原状——他们可能只是目标应用社交库还没加载完。
     *
     * 每日同步跑过之后仍需要调用它：剪枝留下的 REMOVED 标记不会自己消失，
     * 而同步入口当天已经关闭，不在这里补一刀，误判的好友要挂到第二天。
     *
     * @return 关系被改写（含从 REMOVED 恢复）的好友数量
     */
    @JvmStatic
    @Synchronized
    fun refreshRelationsFromSnapshot(userId: String? = UserMap.currentUid): Int {
        val safeUserId = userId?.trim().orEmpty()
        if (safeUserId.isEmpty()) return 0
        val currentUsers = UserMap.getUserMap()
        if (currentUsers.isEmpty()) return 0
        val config = current(safeUserId)
        var changed = 0
        for ((friendUserId, entity) in currentUsers) {
            val normalizedId = friendUserId.trim()
            if (normalizedId.isEmpty() || normalizedId == safeUserId) continue
            val profile = config.profiles[normalizedId] ?: FriendProfile(userId = normalizedId)
            val beforeRemoved = profile.removed
            val beforeRelation = profile.relation
            applyUserEntity(profile, entity, safeUserId)
            config.profiles[normalizedId] = profile
            if (beforeRemoved || beforeRelation != profile.relation) {
                changed++
            }
        }
        if (changed > 0) {
            pruneGroups(config)
            save(safeUserId, config)
            Log.runtime(TAG, "好友关系已按当前快照重算: $changed 个变化，profiles=${config.profiles.size}")
        }
        return changed
    }
    // [fork:friendheal:repo]
'''

# ---- 2. ApplicationHook：跳过分之前先自愈 ----
HOOK_ANCHOR = """            if (!force && Status.hasFlagToday(StatusFlags.FLAG_FRIEND_CENTER_SYNC_TODAY)) {
                val config = FriendRepository.current(safeUserId)
"""
HOOK_SNIPPET = """                FriendRepository.refreshRelationsFromSnapshot(safeUserId) // [fork:friendheal:hook]
"""

# ---- 3. FriendGuard：跳过日志按窗口聚合 ----
IMPORT_ANCHOR = "import io.github.aoguai.sesameag.util.maps.UserMap\n"
IMPORT_SNIPPET = """import java.util.concurrent.ConcurrentHashMap // [fork:friendheal:import]
import java.util.concurrent.atomic.AtomicInteger
"""

GUARD_ANCHOR = """        if (relation != FriendRelation.MUTUAL) {
            val maskName = UserMap.getMaskName(normalized) ?: normalized
            Log.record(
                logTag,
                "$sceneName 跳过[$maskName]：单向好友或已失效(relation=$relation)"
            )
            return true
        }
        return false
    }
}
"""
GUARD_SNIPPET = '''        if (relation != FriendRelation.MUTUAL) {
            val maskName = UserMap.getMaskName(normalized) ?: normalized
            logSkippedNonMutual(logTag, sceneName, maskName, relation)
            return true
        }
        return false
    }

    // 单向/失效好友在收能量这类循环里是成批出现的（一次几十个，每轮都来一遍），
    // 逐条记录会把整份日志冲掉。按场景开 60 秒窗口：窗口内第一条立即记录，
    // 附带同期被折叠的数量，其余只计数。// [fork:friendheal:guard]
    private const val SKIP_LOG_WINDOW_MS = 60_000L

    private class SkipWindow {
        val pending = AtomicInteger(0)

        @Volatile
        var lastLoggedAt: Long = 0L
    }

    private val skipWindows = ConcurrentHashMap<String, SkipWindow>()

    private fun logSkippedNonMutual(
        logTag: String,
        sceneName: String,
        maskName: String,
        relation: FriendRelation
    ) {
        val window = skipWindows.getOrPut(sceneName) { SkipWindow() }
        val count = window.pending.incrementAndGet()
        val now = System.currentTimeMillis()
        if (now - window.lastLoggedAt < SKIP_LOG_WINDOW_MS) {
            return
        }
        window.lastLoggedAt = now
        window.pending.set(0)
        val folded = count - 1
        val tail = if (folded > 0) "（同期另折叠 $folded 个同类跳过）" else ""
        Log.record(logTag, "$sceneName 跳过[$maskName]：单向好友或已失效(relation=$relation)$tail")
    }
}
'''


def apply(patch):
    repo = patch.edit(SRC + "util/friend/FriendRepository.kt")
    repo.insert_after(REPO_ANCHOR, REPO_SNIPPET, "repo")

    hook = patch.edit(SRC + "hook/ApplicationHook.kt")
    hook.insert_after(HOOK_ANCHOR, HOOK_SNIPPET, "hook")

    guard = patch.edit(SRC + "util/FriendGuard.kt")
    guard.insert_after(IMPORT_ANCHOR, IMPORT_SNIPPET, "import")
    guard.replace(GUARD_ANCHOR, GUARD_SNIPPET, "guard")


if __name__ == "__main__":
    run(TAG, apply)
