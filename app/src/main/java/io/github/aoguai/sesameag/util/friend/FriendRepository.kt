package io.github.aoguai.sesameag.util.friend

import com.fasterxml.jackson.core.type.TypeReference
import io.github.aoguai.sesameag.entity.UserEntity
import io.github.aoguai.sesameag.entity.friend.FriendCenterConfig
import io.github.aoguai.sesameag.entity.friend.FriendGroup
import io.github.aoguai.sesameag.entity.friend.FriendModuleCapability
import io.github.aoguai.sesameag.entity.friend.FriendProfile
import io.github.aoguai.sesameag.entity.friend.FriendRelation
import io.github.aoguai.sesameag.util.Files
import io.github.aoguai.sesameag.util.JsonUtil
import io.github.aoguai.sesameag.util.Log
import io.github.aoguai.sesameag.util.maps.UserMap
import java.util.UUID

object FriendRepository {
    private const val TAG = "FriendRepository"
    const val SCHEMA_VERSION = 1
    const val MUTUAL_FRIEND_STATUS = 1

    @Volatile
    private var loadedUserId: String? = null

    @Volatile
    private var loadedConfig: FriendCenterConfig = FriendCenterConfig()

    @Volatile
    private var loadedLastModified: Long = 0L

    @Volatile
    private var loadedFileLength: Long = 0L

    @JvmStatic
    @Synchronized
    fun load(userId: String? = UserMap.currentUid): FriendCenterConfig {
        val safeUserId = userId?.trim().orEmpty()
        if (safeUserId.isEmpty()) {
            return FriendCenterConfig()
        }

        val file = Files.getFriendCenterFile(safeUserId)
        val config = try {
            val body = Files.readFromFile(file)
            if (body.isBlank()) {
                FriendCenterConfig(userId = safeUserId)
            } else {
                JsonUtil.parseObject(body, object : TypeReference<FriendCenterConfig>() {})
            }
        } catch (t: Throwable) {
            Log.printStackTrace(TAG, "加载好友中心失败，使用空配置", t)
            FriendCenterConfig(userId = safeUserId)
        }

        normalizeConfig(config, safeUserId)
        loadedUserId = safeUserId
        loadedConfig = config
        loadedLastModified = file.lastModified()
        loadedFileLength = file.length()
        if (
            config.profiles.isEmpty() &&
            UserMap.currentUid == safeUserId &&
            UserMap.getUserMap().isNotEmpty()
        ) {
            return mergeFromUserMap(safeUserId)
        }
        if (file.length() <= 0L) {
            save(safeUserId, config)
        }
        return config
    }

    @JvmStatic
    @Synchronized
    fun save(userId: String? = loadedUserId, config: FriendCenterConfig = loadedConfig): Boolean {
        val safeUserId = userId?.trim().orEmpty()
        if (safeUserId.isEmpty()) return false
        var targetConfig = config
        if (config === loadedConfig && loadedUserId != safeUserId) {
            targetConfig = load(safeUserId)
        }
        normalizeConfig(targetConfig, safeUserId)
        return try {
            val file = Files.getFriendCenterFile(safeUserId)
            val success = Files.write2File(JsonUtil.formatJson(targetConfig), file)
            if (success) {
                loadedUserId = safeUserId
                loadedConfig = targetConfig
                loadedLastModified = file.lastModified()
                loadedFileLength = file.length()
            } else {
                invalidateLoaded(safeUserId)
            }
            success
        } catch (t: Throwable) {
            invalidateLoaded(safeUserId)
            Log.printStackTrace(TAG, "保存好友中心失败", t)
            false
        }
    }

    @JvmStatic
    @Synchronized
    fun current(userId: String? = UserMap.currentUid): FriendCenterConfig {
        val safeUserId = userId?.trim().orEmpty()
        if (safeUserId.isEmpty()) {
            return FriendCenterConfig()
        }
        return if (safeUserId.isNotEmpty() && loadedUserId == safeUserId && !isLoadedFileStale(safeUserId)) {
            loadedConfig
        } else {
            load(safeUserId)
        }
    }

    @JvmStatic
    @Synchronized
    /**
     * 合并 UserMap 到好友中心。
     *
     * @param allowPruneMissing 是否把“当前快照中缺失的历史好友”标记为 REMOVED。
     * 仅在快照来源可信（如 Hook 实时好友缓存）时开启，避免本地缓存不完整时误判失效。
     */
    fun mergeFromUserMap(
        userId: String? = UserMap.currentUid,
        previousUsers: Map<String, UserEntity> = emptyMap(),
        allowPruneMissing: Boolean = false
    ): FriendCenterConfig {
        val safeUserId = userId?.trim().orEmpty()
        if (safeUserId.isEmpty()) {
            return FriendCenterConfig()
        }
        val currentUsers = UserMap.getUserMap()
        val config = current(safeUserId)
        if (currentUsers.isEmpty()) {
            return config
        }

        val nowIds = currentUsers.keys.toSet()
        val previousIds = previousUsers.keys.toSet()
        val removedIds = linkedSetOf<String>()
        (previousIds + config.profiles.keys).forEach { candidateId ->
            if (candidateId.isBlank() || candidateId == safeUserId || nowIds.contains(candidateId)) {
                return@forEach
            }
            val profile = config.profiles[candidateId]
            // [fork:friendprune:allow] 与上游 0.2.6 对齐：只有显式 allowPruneMissing 才允许剪枝。
            // 原来 previousIds 命中即可剪，调用方漏传参数时会把好友整片误判成失效。
            val shouldMarkRemoved = allowPruneMissing && (
                previousIds.contains(candidateId) || (
                    profile != null &&
                        profile.relation != FriendRelation.UNKNOWN &&
                        profile.relation != FriendRelation.SELF
                    )
                )
            if (shouldMarkRemoved) {
                removedIds.add(candidateId)
            }
        }

        // [fork:friendprune:guard] 一次同步要把超过一半的有效好友判成失效，几乎只能是
        // 好友快照不完整（目标应用社交库尚未加载完）。这种情况宁可不剪，也不要把整片好友标死。
        val validProfileCount =
            config.profiles.values.count {
                !it.removed &&
                    it.relation != FriendRelation.UNKNOWN &&
                    it.relation != FriendRelation.SELF
            }
        if (validProfileCount >= 5 && removedIds.size * 2 > validProfileCount) {
            Log.runtime(
                TAG,
                "好友剪枝已拦截：待失效 ${removedIds.size} 个 / 现有有效 $validProfileCount 个，" +
                    "疑似好友快照不完整，保留原有关系"
            )
            removedIds.clear()
        }

        for ((friendUserId, entity) in currentUsers) {
            val normalizedId = friendUserId.trim()
            if (normalizedId.isEmpty()) continue
            val profile = config.profiles[normalizedId] ?: FriendProfile(userId = normalizedId)
            applyUserEntity(profile, entity, safeUserId)
            config.profiles[normalizedId] = profile
        }

        removedIds.forEach { removedId ->
            val profile = config.profiles[removedId] ?: FriendProfile(userId = removedId)
            profile.removed = true
            profile.relation = FriendRelation.REMOVED
            config.profiles[removedId] = profile
        }

        pruneGroups(config)
        save(safeUserId, config)
        Log.runtime(TAG, "好友中心刷新完成: profiles=${config.profiles.size}, groups=${config.groups.size}")
        return config
    }

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

    @JvmStatic
    fun listProfiles(userId: String? = UserMap.currentUid): List<FriendProfile> {
        return current(userId).profiles.values.sortedWith(compareByDescending<FriendProfile> {
            it.globalPinned
        }.thenBy { it.displayName.ifBlank { it.userId } })
    }

    @JvmStatic
    fun relationOf(userId: String?): FriendRelation {
        val normalized = userId?.trim().orEmpty()
        if (normalized.isEmpty()) return FriendRelation.UNKNOWN
        if (normalized == UserMap.currentUid) return FriendRelation.SELF
        current().profiles[normalized]?.let { profile ->
            if (profile.removed || profile.relation == FriendRelation.REMOVED) {
                return FriendRelation.REMOVED
            }
            if (profile.relation != FriendRelation.UNKNOWN) {
                return profile.relation
            }
        }
        val userEntity = UserMap.get(normalized) ?: return FriendRelation.UNKNOWN
        return when {
            userEntity.friendStatus == MUTUAL_FRIEND_STATUS -> FriendRelation.MUTUAL
            userEntity.friendStatus != null -> FriendRelation.ONE_WAY
            else -> FriendRelation.UNKNOWN
        }
    }

    @JvmStatic
    fun isGlobalBlocked(userId: String?): Boolean {
        val normalized = userId?.trim().orEmpty()
        if (normalized.isEmpty()) return false
        return current().profiles[normalized]?.globalBlocked == true
    }

    @JvmStatic
    @Synchronized
    fun markRemoved(ownerUserId: String?, friendUserId: String?): Boolean {
        val safeOwner = ownerUserId?.trim().orEmpty()
        val safeFriend = friendUserId?.trim().orEmpty()
        if (safeOwner.isEmpty() || safeFriend.isEmpty() || safeOwner == safeFriend) return false
        val config = current(safeOwner)
        val profile = config.profiles[safeFriend] ?: FriendProfile(userId = safeFriend)
        profile.removed = true
        profile.relation = FriendRelation.REMOVED
        config.profiles[safeFriend] = profile
        return save(safeOwner, config)
    }

    @JvmStatic
    @Synchronized
    fun upsertGroup(userId: String?, group: FriendGroup): FriendGroup {
        val now = System.currentTimeMillis()
        val normalizedGroup = group.copy(
            id = group.id.trim().ifBlank { UUID.randomUUID().toString() },
            name = group.name.trim().ifBlank { "未命名分组" },
            memberIds = linkedSetOf<String>().apply {
                group.memberIds.mapNotNullTo(this) { it.trim().takeIf(String::isNotEmpty) }
            },
            createdAt = if (group.createdAt > 0L) group.createdAt else now,
            updatedAt = now
        )
        val safeUserId = userId?.trim().orEmpty()
        if (safeUserId.isEmpty()) {
            Log.runtime(TAG, "upsertGroup 跳过：userId为空")
            return normalizedGroup
        }
        val config = current(safeUserId)
        val index = config.groups.indexOfFirst { it.id == normalizedGroup.id }
        if (index >= 0) {
            config.groups[index] = normalizedGroup
        } else {
            config.groups.add(normalizedGroup)
        }
        pruneGroups(config)
        save(safeUserId, config)
        return normalizedGroup
    }

    @JvmStatic
    @Synchronized
    fun deleteGroup(userId: String?, groupId: String): Boolean {
        val safeUserId = userId?.trim().orEmpty()
        if (safeUserId.isEmpty()) {
            Log.runtime(TAG, "deleteGroup 跳过：userId为空")
            return false
        }
        val safeGroupId = groupId.trim()
        if (safeGroupId.isEmpty()) {
            return false
        }
        val config = current(safeUserId)
        val removed = config.groups.removeAll { it.id == safeGroupId }
        return removed && save(safeUserId, config)
    }

    @JvmStatic
    @Synchronized
    fun recordCapability(
        ownerUserId: String?,
        friendUserId: String?,
        moduleKey: String,
        capability: FriendModuleCapability
    ): Boolean {
        val safeOwner = ownerUserId?.trim().orEmpty()
        val safeFriend = friendUserId?.trim().orEmpty()
        val safeModule = moduleKey.trim()
        if (safeOwner.isEmpty() || safeFriend.isEmpty() || safeModule.isEmpty()) return false

        val config = current(safeOwner)
        val profile = config.profiles[safeFriend] ?: FriendProfile(userId = safeFriend)
        if (!profile.removed && profile.relation != FriendRelation.REMOVED) {
            UserMap.get(safeFriend)?.let { applyUserEntity(profile, it, safeOwner) }
        }
        val existingCapability = profile.capabilities[safeModule]
        if (
            existingCapability != null &&
            existingCapability.state == capability.state &&
            existingCapability.source == capability.source &&
            existingCapability.reason == capability.reason
        ) {
            return true
        }
        profile.capabilities[safeModule] = capability
        config.profiles[safeFriend] = profile
        return save(safeOwner, config)
    }

    private fun normalizeConfig(config: FriendCenterConfig, userId: String) {
        config.schemaVersion = SCHEMA_VERSION
        config.userId = userId
        val normalizedProfiles = linkedMapOf<String, FriendProfile>()
        for ((rawId, rawProfile) in config.profiles) {
            val normalizedId = rawProfile.userId.ifBlank { rawId }.trim()
            if (normalizedId.isEmpty()) continue
            rawProfile.userId = normalizedId
            rawProfile.displayName = rawProfile.displayName.trim()
            when {
                normalizedId == userId -> {
                    rawProfile.removed = false
                    rawProfile.relation = FriendRelation.SELF
                }
                rawProfile.removed || rawProfile.relation == FriendRelation.REMOVED -> {
                    rawProfile.removed = true
                    rawProfile.relation = FriendRelation.REMOVED
                }
            }
            normalizedProfiles[normalizedId] = rawProfile
        }
        config.profiles = normalizedProfiles
        pruneGroups(config)
    }

    private fun isLoadedFileStale(userId: String): Boolean {
        return runCatching {
            val file = Files.getFriendCenterFile(userId)
            val modifiedAt = file.lastModified()
            val length = file.length()
            modifiedAt != loadedLastModified || length != loadedFileLength
        }.getOrDefault(false)
    }

    private fun invalidateLoaded(userId: String) {
        if (loadedUserId != userId) return
        loadedUserId = null
        loadedConfig = FriendCenterConfig()
        loadedLastModified = 0L
        loadedFileLength = 0L
    }

    private fun applyUserEntity(profile: FriendProfile, entity: UserEntity, currentUserId: String) {
        val userId = entity.userId?.trim().orEmpty()
        profile.userId = userId
        profile.displayName = entity.showName.ifBlank { entity.fullName }.ifBlank { userId }
        profile.friendStatus = entity.friendStatus
        profile.removed = false
        profile.relation = when {
            userId == currentUserId -> FriendRelation.SELF
            entity.friendStatus == MUTUAL_FRIEND_STATUS -> FriendRelation.MUTUAL
            entity.friendStatus != null -> FriendRelation.ONE_WAY
            else -> FriendRelation.UNKNOWN
        }
    }

    private fun pruneGroups(config: FriendCenterConfig) {
        val knownIds = config.profiles.keys
        val normalizedGroups = mutableListOf<FriendGroup>()
        val seenGroupIds = linkedSetOf<String>()
        config.groups.forEach { group ->
            val normalizedGroupId = group.id.trim()
            if (normalizedGroupId.isEmpty()) {
                return@forEach
            }
            if (!seenGroupIds.add(normalizedGroupId)) {
                Log.runtime(TAG, "检测到重复分组ID[$normalizedGroupId]，仅保留首个分组")
                return@forEach
            }
            group.id = normalizedGroupId
            group.name = group.name.trim().ifBlank { "未命名分组" }
            group.memberIds = linkedSetOf<String>().apply {
                group.memberIds
                    .mapNotNull { it.trim().takeIf(String::isNotEmpty) }
                    .filter { knownIds.isEmpty() || knownIds.contains(it) }
                    .forEach { add(it) }
            }
            normalizedGroups.add(group)
        }
        config.groups.clear()
        config.groups.addAll(normalizedGroups)
    }
}
