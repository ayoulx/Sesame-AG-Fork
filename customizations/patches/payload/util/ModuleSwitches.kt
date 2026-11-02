package io.github.aoguai.sesameag.util

import io.github.aoguai.sesameag.util.Log.printStackTrace
import org.json.JSONObject
import java.io.File

/**
 * 模块级开关。
 *
 * 放在 [Files.CONFIG_DIR] 下的单一 JSON 文件里，模块进程写、宿主进程读，
 * 不依赖框架的 remote preferences 能力，也不要求先打开模块 App。
 * 文件不存在即视为全部开关关闭。
 */
object ModuleSwitches {
    private const val TAG = "ModuleSwitches"
    private const val FILE_NAME = "module_switches.json"
    private const val KEY_CAPTCHA_SOLVER = "captchaSolver"

    private class Snapshot(val stamp: Long, val captchaSolver: Boolean)

    @Volatile
    private var cached: Snapshot? = null

    private fun file(): File = File(Files.CONFIG_DIR, FILE_NAME)

    /** 滑块验证开关，默认关闭 */
    fun isCaptchaSolverEnabled(): Boolean = current().captchaSolver

    fun setCaptchaSolverEnabled(enabled: Boolean): Boolean {
        synchronized(this) {
            val target = file()
            val root = readJson(target)
            root.put(KEY_CAPTCHA_SOLVER, enabled)
            val written = Files.write2File(root.toString(2), target)
            cached = Snapshot(if (target.exists()) target.lastModified() else 0L, enabled)
            return written
        }
    }

    private fun current(): Snapshot {
        val target = file()
        val stamp = if (target.exists()) target.lastModified() else 0L
        cached?.let { if (it.stamp == stamp) return it }
        val value =
            try {
                if (target.exists()) readJson(target).optBoolean(KEY_CAPTCHA_SOLVER, false) else false
            } catch (t: Throwable) {
                printStackTrace(TAG, "读取模块开关失败，按关闭处理", t)
                false
            }
        return Snapshot(stamp, value).also { cached = it }
    }

    private fun readJson(target: File): JSONObject =
        try {
            if (target.exists()) JSONObject(target.readText()) else JSONObject()
        } catch (_: Throwable) {
            JSONObject()
        }
}
