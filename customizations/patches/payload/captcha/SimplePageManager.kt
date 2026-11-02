package io.github.aoguai.sesameag.hook.captcha

import android.app.Activity
import android.app.Application
import android.app.Dialog
import io.github.aoguai.sesameag.hook.ApplicationHook
import io.github.aoguai.sesameag.util.Log
import kotlinx.coroutines.CoroutineScope
import kotlinx.coroutines.Dispatchers
import kotlinx.coroutines.delay
import kotlinx.coroutines.launch
import java.lang.ref.WeakReference
import java.util.concurrent.ConcurrentHashMap

/**
 * 只做两件事：盯住顶层 Activity、盯住验证码弹窗，然后在弹窗出现后把控制权交给处理器。
 *
 * 相比参考实现去掉了「Hook 所有 Dialog 构造函数」的全量监听：
 * 验证码弹窗类名固定，只挂它的 show() 就够，既省开销也避免误伤目标应用的其它弹窗。
 */
object SimplePageManager {

    private const val TAG = "CaptchaPage"
    private const val CAPTCHA_DIALOG_CLASS = "com.alipay.rdssecuritysdk.v3.captcha.view.CaptchaDialog"
    private const val RETRY_TIMES = 10
    private const val RETRY_DELAY_MS = 500L

    interface ActivityFocusHandler {
        /** 返回 true 表示已处理完成，不再重试。 */
        suspend fun handle(activity: Activity): Boolean
    }

    private val handlers = ConcurrentHashMap<String, ActivityFocusHandler>()
    private val dialogs = ArrayList<WeakReference<Dialog>>()

    @Volatile
    private var topActivity: Activity? = null

    @Volatile
    private var busy = false

    fun install(classLoader: ClassLoader) {
        hookTopActivity()
        hookCaptchaDialog(classLoader)
    }

    fun addHandler(activityClassName: String, handler: ActivityFocusHandler) {
        handlers[activityClassName] = handler
    }

    /** 在所有已知验证码弹窗里按 XPath 找第一个命中节点。 */
    fun findTopView(xpath: String): SimpleViewImage? {
        dialogs.removeAll { it.get() == null }
        for (reference in dialogs) {
            val dialog = reference.get() ?: continue
            if (!dialog.isShowing) continue
            val decorView = dialog.window?.decorView ?: continue
            val hit = SimpleXpathParser.evaluate(SimpleViewImage(decorView), xpath).firstOrNull()
            if (hit != null) return hit
        }
        return null
    }

    private fun hookTopActivity() {
        try {
            val method = Application::class.java.getDeclaredMethod("dispatchActivityResumed", Activity::class.java)
            ApplicationHook.requireXposedInterface().hook(method).intercept { chain ->
                (chain.args.getOrNull(0) as? Activity)?.let { topActivity = it }
                chain.proceed()
            }
        } catch (t: Throwable) {
            Log.printStackTrace(TAG, "挂钩 dispatchActivityResumed 失败", t)
        }
    }

    private fun hookCaptchaDialog(classLoader: ClassLoader) {
        try {
            val captchaDialog = Class.forName(CAPTCHA_DIALOG_CLASS, false, classLoader)
            val showMethod = captchaDialog.getDeclaredMethod("show")
            ApplicationHook.requireXposedInterface().hook(showMethod).intercept { chain ->
                val result = chain.proceed()
                (chain.getThisObject() as? Dialog)?.let { dialog ->
                    trackDialog(dialog)
                    trigger("验证码弹窗已显示")
                }
                result
            }
        } catch (t: Throwable) {
            Log.printStackTrace(TAG, "挂钩验证码弹窗失败，自动过滑块不可用", t)
        }
    }

    private fun trackDialog(dialog: Dialog) {
        if (dialogs.none { it.get() === dialog }) {
            dialogs.add(WeakReference(dialog))
        }
    }

    private fun trigger(source: String) {
        val activity = topActivity ?: run {
            Log.debug(TAG, "$source，但当前无顶层 Activity，跳过")
            return
        }
        val handler = handlers[activity.javaClass.name] ?: run {
            Log.debug(TAG, "$source，但 ${activity.javaClass.name} 未注册处理器，跳过")
            return
        }
        if (busy) {
            Log.debug(TAG, "$source，已有处理流程在跑，跳过重复触发")
            return
        }
        busy = true
        CoroutineScope(Dispatchers.Main.immediate).launch {
            try {
                repeat(RETRY_TIMES) { attempt ->
                    delay(RETRY_DELAY_MS)
                    val finished =
                        try {
                            handler.handle(activity)
                        } catch (t: Throwable) {
                            Log.printStackTrace(TAG, "处理验证码失败（第 ${attempt + 1} 次）", t)
                            false
                        }
                    if (finished) return@launch
                }
                Log.error(TAG, "重试 $RETRY_TIMES 次仍未完成滑动验证")
            } finally {
                busy = false
            }
        }
    }
}
