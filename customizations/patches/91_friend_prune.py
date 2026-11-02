#!/usr/bin/env python3
"""好友中心：剪枝必须显式授权，并对「大面积失效」加拦截。

0.1.9 的 mergeFromUserMap 有两个问题，合起来会把整片好友误标成失效并写进 friend.json：

1. `previousIds.contains(candidateId) ||` 在 `allowPruneMissing` 之外，
   只要上一次快照里有这个 id 就剪，调用方漏传参数也照剪。
   上游 0.2.6 已把整段收进 `if (allowPruneMissing)`，这里对齐。
2. 目标应用社交库（AliAccountDaoOp）在冷启动早期可能返回「非空但不完整」的好友快照，
   此时不完整的那部分会被判成 REMOVED。这条靠比例拦截：一次要剪掉超过一半的有效档案，
   就认为快照不可信，保留原关系并告警。
"""

import os
import sys

sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from patchkit import run  # noqa: E402

TAG = "friendprune"
REPO = "app/src/main/java/io/github/aoguai/sesameag/util/friend/FriendRepository.kt"

PRUNE_ANCHOR = """            val shouldMarkRemoved = previousIds.contains(candidateId) || (
                allowPruneMissing &&
                    profile != null &&
                    profile.relation != FriendRelation.UNKNOWN &&
                    profile.relation != FriendRelation.SELF
                )"""

PRUNE_SNIPPET = """            // [fork:friendprune:allow] 与上游 0.2.6 对齐：只有显式 allowPruneMissing 才允许剪枝。
            // 原来 previousIds 命中即可剪，调用方漏传参数时会把好友整片误判成失效。
            val shouldMarkRemoved = allowPruneMissing && (
                previousIds.contains(candidateId) || (
                    profile != null &&
                        profile.relation != FriendRelation.UNKNOWN &&
                        profile.relation != FriendRelation.SELF
                    )
                )"""

GUARD_ANCHOR = """        for ((friendUserId, entity) in currentUsers) {
            val normalizedId = friendUserId.trim()"""

GUARD_SNIPPET = """        // [fork:friendprune:guard] 一次同步要把超过一半的有效好友判成失效，几乎只能是
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
            val normalizedId = friendUserId.trim()"""


def apply(patch):
    repo = patch.edit(REPO)
    repo.replace(PRUNE_ANCHOR, PRUNE_SNIPPET, "allow")
    repo.replace(GUARD_ANCHOR, GUARD_SNIPPET, "guard")


if __name__ == "__main__":
    run(TAG, apply)
