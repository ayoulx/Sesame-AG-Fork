package io.github.aoguai.sesameag.hook

import android.app.Activity
import android.app.Application
import android.os.Bundle
import android.os.Handler
import android.os.Looper
import android.os.SystemClock
import android.view.KeyEvent
import androidx.activity.ComponentActivity
import io.github.aoguai.sesameag.util.Log
import java.lang.ref.WeakReference
import java.util.concurrent.atomic.AtomicLong

/**
 * 在宿主应用内模拟一次「返回」。
 *
 * 命中 1009/系统繁忙 这类风控拦截时，目标应用往往停在一个受限页面或验证码弹窗上，
 * 后续 RPC 全部被拦。在宿主应用里退一步，多半能回到正常页面。
 *
 * 作用范围刻意做得极窄：
 * - 只投递给宿主应用自己当前 resumed 的 Activity，走它自己的返回逻辑；
 * - 不调用 root 命令、不用 Shizuku、不做系统级输入注入（不需要 INJECT_EVENTS 权限），
 *   所以不会误触别的应用，也不会在系统层面留下痕迹；
 * - 页面上没有可用 Activity 时只记一条日志并放弃。
 *
 * 用 [Application.ActivityLifecycleCallbacks] 跟踪前台页面，不依赖隐藏 API。
 */
object HostBack {

    private const val TAG = "HostBack"

    /** 两次返回之间至少隔这么久，避免风控连着来时把页面一路退到底。 */
    private const val MIN_INTERVAL_MS = 3_000L

    @Volatile
    private var current: WeakReference<Activity>? = null

    @Volatile
    private var attached = false

    private val lastPressedAt = AtomicLong(0L)

    fun attach(application: Application?) {
        if (attached || application == null) return
        attached = true
        runCatching {
            application.registerActivityLifecycleCallbacks(
                object : Application.ActivityLifecycleCallbacks {
                    override fun onActivityResumed(activity: Activity) {
                        current = WeakReference(activity)
                    }

                    override fun onActivityPaused(activity: Activity) {
                        if (current?.get() === activity) current = null
                    }

                    override fun onActivityDestroyed(activity: Activity) {
                        if (current?.get() === activity) current = null
                    }

                    override fun onActivityCreated(activity: Activity, savedInstanceState: Bundle?) = Unit

                    override fun onActivityStarted(activity: Activity) = Unit

                    override fun onActivityStopped(activity: Activity) = Unit

                    override fun onActivitySaveInstanceState(activity: Activity, outState: Bundle) = Unit
                },
            )
        }.onFailure {
            Log.record(TAG, "宿主页面跟踪注册失败，风控时无法自动返回: ${it.javaClass.simpleName}")
        }
    }

    /**
     * 对宿主当前页面按一次返回。
     *
     * @return true 表示已经投递出去（不代表页面一定响应）。
     */
    fun pressBack(reason: String): Boolean {
        val now = SystemClock.uptimeMillis()
        if (now - lastPressedAt.get() < MIN_INTERVAL_MS) {
            return false
        }
        val activity = current?.get()
        if (activity == null || activity.isFinishing) {
            Log.record(TAG, "需要返回（$reason），但宿主当前没有可用页面，跳过")
            return false
        }
        lastPressedAt.set(now)
        val name = activity.javaClass.simpleName
        Handler(Looper.getMainLooper()).post {
            dispatchBack(activity)
            Log.record(TAG, "已在宿主应用内模拟返回：$name（$reason）")
        }
        return true
    }

    private fun dispatchBack(activity: Activity) {
        if (activity.isFinishing) return
        try {
            // androidx 页面优先走返回回调，这样能正确触发返回栈与拦截器；
            // 非 androidx 页面（宿主里有不少）退回按键事件，仍只走它自己的分发链路。
            if (activity is ComponentActivity) {
                activity.onBackPressedDispatcher.onBackPressed()
                return
            }
            activity.dispatchKeyEvent(KeyEvent(KeyEvent.ACTION_DOWN, KeyEvent.KEYCODE_BACK))
            activity.dispatchKeyEvent(KeyEvent(KeyEvent.ACTION_UP, KeyEvent.KEYCODE_BACK))
        } catch (t: Throwable) {
            Log.record(TAG, "宿主页面返回失败: ${t.javaClass.simpleName} ${t.message}")
        }
    }
}
