package io.github.aoguai.sesameag.util

import java.util.concurrent.ConcurrentHashMap
import java.util.concurrent.atomic.AtomicInteger

/**
 * 「注定失败」类提示的折叠器。
 *
 * 开着「禁止系统调度前台拉起目标应用」时，每个蹲点、每个持久子任务都会各自
 * 播报一次降级，一次运行能刷出几百行同一个意思，把真正有用的进度全顶出视野。
 * 这类提示的根因只有一个，不需要逐条出现。
 *
 * 同一个 key 只在第一次详细记录，之后每 [step] 次汇报一次累计数量。
 * 计数只在本进程内有效——进程重启后重新开始，这正好对应「新一轮运行」。
 */
object LogFold {

    private val counters = ConcurrentHashMap<String, AtomicInteger>()

    /**
     * 记一次同类事件。
     *
     * @return 本次累计数（第 1 次或每满 [step] 次），返回 null 表示这一条应当折叠掉。
     */
    fun tick(key: String, step: Int = 50): Int? {
        val count = counters.getOrPut(key) { AtomicInteger(0) }.incrementAndGet()
        if (count == 1) return count
        if (step <= 1) return count
        return if (count % step == 0) count else null
    }

    /** 累计次数，供需要收尾汇总的地方使用。 */
    fun count(key: String): Int = counters[key]?.get() ?: 0

    /**
     * 降级提示的折叠尾注：第一次说明原因，之后只报累计数量。
     *
     * 森林、庄园、运动、新村四处共用同一套措辞，避免每处各写一遍同样的判断。
     * 放在对象里而不是顶层，是为了让 import LogFold 的文件不必再单独 import 它。
     */
    fun foldedTail(total: Int): String =
        if (total == 1) {
            "（禁止系统调度前台拉起目标应用；同类提示每 20 个汇总一次）"
        } else {
            "，同类累计 $total 个"
        }
}
