package io.github.aoguai.sesameag.hook.captcha

import io.github.aoguai.sesameag.entity.AlipayVersion
import io.github.aoguai.sesameag.hook.ApplicationHook
import io.github.aoguai.sesameag.util.Log
import io.github.aoguai.sesameag.util.ModuleSwitches

/**
 * 滑块验证的总开关与挂钩入口。
 *
 * 两道门禁：
 * 1. 用户在设置里打开（[ModuleSwitches.isCaptchaSolverEnabled]，默认关闭）；
 * 2. 目标应用版本 ≤ [MAX_SUPPORTED_VERSION]，超出版本不做任何挂钩。
 */
object CaptchaSolver {

    private const val TAG = "CaptchaSolver"

    private const val XRIVER_ACTIVITY = "com.alipay.mobile.nebulax.xriver.activity.XRiverActivity"
    private const val LAUNCHER_ACTIVITY = "com.eg.android.AlipayGphone.AlipayLogin"

    /** 界面自动化只在 10.6.58 及更早的验证码弹窗上验证过。 */
    val MAX_SUPPORTED_VERSION: AlipayVersion = AlipayVersion("10.6.58.99999")

    @Volatile
    private var installed = false

    @Volatile
    private var unsupportedReported = false

    fun install(classLoader: ClassLoader) {
        if (installed) return
        if (!ModuleSwitches.isCaptchaSolverEnabled()) {
            Log.debug(TAG, "开关未开启，不做滑块挂钩")
            return
        }
        val version = ApplicationHook.alipayVersion
        if (!isSupported(version)) {
            if (!unsupportedReported) {
                unsupportedReported = true
                Log.record(TAG, "目标应用 $version 超出滑块验证支持范围（≤ $MAX_SUPPORTED_VERSION），已跳过")
            }
            return
        }
        installed = true
        SimplePageManager.install(classLoader)
        val handler = SlideCaptchaHandler()
        SimplePageManager.addHandler(XRIVER_ACTIVITY, handler)
        SimplePageManager.addHandler(LAUNCHER_ACTIVITY, handler)
        Log.record(TAG, "滑块验证已启用，目标应用版本 $version")
    }

    fun isSupported(version: AlipayVersion): Boolean {
        if (version.toString().isEmpty()) return false
        return version <= MAX_SUPPORTED_VERSION
    }
}
