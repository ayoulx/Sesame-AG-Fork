package io.github.aoguai.sesameag.util

import io.github.aoguai.sesameag.entity.friend.FriendRelation
import io.github.aoguai.sesameag.util.friend.FriendRepository
import io.github.aoguai.sesameag.util.maps.UserMap
import java.util.concurrent.ConcurrentHashMap // [fork:friendheal:import]
import java.util.concurrent.atomic.AtomicInteger

/**
 * 好友关系守卫：
 * - 排除当前账号自己
 * - 排除单向好友/已失效好友
 */
object FriendGuard {
    const val MUTUAL_FRIEND_STATUS = 1

    @JvmStatic
    fun normalizeUserId(userId: String?): String? {
        val normalized = userId?.trim().orEmpty()
        return normalized.ifEmpty { null }
    }

    @JvmStatic
    fun isSelf(userId: String?): Boolean {
        val normalized = normalizeUserId(userId) ?: return false
        return normalized == UserMap.currentUid
    }

    @JvmStatic
    fun isMutualFriend(userId: String?): Boolean {
        val normalized = normalizeUserId(userId) ?: return false
        if (normalized == UserMap.currentUid) {
            return false
        }
        return FriendRepository.relationOf(normalized) == FriendRelation.MUTUAL
    }

    @JvmStatic
    fun shouldSkipFriend(
        userId: String?,
        logTag: String,
        sceneName: String,
        skipSelf: Boolean = true
    ): Boolean {
        val normalized = normalizeUserId(userId)
        if (normalized == null) {
            Log.record(logTag, "$sceneName 跳过：userId为空")
            return true
        }
        if (skipSelf && normalized == UserMap.currentUid) {
            Log.record(logTag, "$sceneName 跳过自己账号[$normalized]")
            return true
        }
        val relation = FriendRepository.relationOf(normalized)
        if (relation == FriendRelation.UNKNOWN) {
            Log.record(logTag, "$sceneName 跳过[$normalized]：好友信息不存在")
            return true
        }
        if (FriendRepository.isGlobalBlocked(normalized)) {
            val maskName = UserMap.getMaskName(normalized) ?: normalized
            Log.record(logTag, "$sceneName 跳过[$maskName]：好友中心全局黑名单")
            return true
        }
        if (relation != FriendRelation.MUTUAL) {
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
