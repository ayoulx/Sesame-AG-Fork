package io.github.aoguai.sesameag.hook.captcha

import android.app.Activity
import android.view.View
import io.github.aoguai.sesameag.util.Log
import io.github.aoguai.sesameag.util.ModuleSwitches
import kotlinx.coroutines.delay
import kotlinx.coroutines.sync.Mutex
import kotlin.random.Random

/**
 * 目标应用「向右滑动验证」的处理器。
 *
 * 流程：找文本锚点 → 等界面稳定 → 定位滑块容器 → 换算绝对坐标 → 合成滑动 → 复查文本是否消失。
 * 一轮只滑一次：滑完无论成败都返回已处理，避免连续重试把风控打醒；
 * 只有「文本还没渲染出来」才返回未处理，交给 [SimplePageManager] 继续等。
 */
class SlideCaptchaHandler : SimplePageManager.ActivityFocusHandler {

    override suspend fun handle(activity: Activity): Boolean {
        // 开关在触发时判定，而不是挂钩时判定：用户随时可以关掉，不需要重启目标应用。
        if (!ModuleSwitches.isCaptchaSolverEnabled()) {
            Log.record(TAG, "检测到滑块验证，但开关未开启，本轮跳过")
            return true
        }
        if (!mutex.tryLock()) return true
        try {
            val anchor = SimplePageManager.findTopView(SLIDE_TEXT_XPATH)
            if (anchor == null) return false

            delay(SETTLE_DELAY_MS)
            val slider = ViewHierarchyAnalyzer.findActualSliderView(anchor) ?: run {
                Log.error(TAG, "找到验证文本但没找到滑块，放弃本轮")
                return true
            }
            val coordinates = calculateCoordinates(activity, slider) ?: run {
                Log.error(TAG, "滑动坐标换算失败，放弃本轮")
                return true
            }
            Log.record(TAG, "起点=[${coordinates.startX},${coordinates.startY}] 终点=[${coordinates.endX},${coordinates.endY}]")
            MotionEventSimulator.swipe(
                view = slider,
                startX = coordinates.startX,
                startY = coordinates.startY,
                endX = coordinates.endX,
                endY = coordinates.endY,
                durationMs = Random.nextLong(DURATION_MIN_MS, DURATION_MAX_MS + 1),
            )

            delay(POST_SLIDE_DELAY_MS)
            val stillThere = SimplePageManager.findTopView(SLIDE_TEXT_XPATH) != null
            if (stillThere) {
                Log.error(TAG, "滑动后验证文本仍在，本轮视为失败")
            } else {
                Log.record(TAG, "滑动验证已通过")
            }
            return true
        } finally {
            mutex.unlock()
        }
    }

    private fun calculateCoordinates(activity: Activity, slider: View): SlideCoordinates? {
        val container = slider.parent as? View ?: return null
        val containerBox = IntArray(2).also { container.getLocationOnScreen(it) }
        val sliderBox = IntArray(2).also { slider.getLocationOnScreen(it) }
        if (slider.width <= 0 || slider.height <= 0) return null

        val startX = sliderBox[0] + slider.width / 2f + START_OFFSET_PX + Random.nextInt(-3, 4)
        val startY = sliderBox[1] + slider.height / 2f + Random.nextInt(-2, 3)

        val screenWidth = activity.resources.displayMetrics.widthPixels.toFloat()
        val containerRight = containerBox[0] + container.width
        var endX = containerRight - END_MARGIN_PX + Random.nextInt(-5, 6)
        endX = minOf(endX, screenWidth - SCREEN_EDGE_PX)

        val minDistance = slider.width * MIN_DISTANCE_RATIO
        if (endX - startX < minDistance) {
            endX = minOf(startX + minDistance + Random.nextInt(-3, 4), screenWidth - SCREEN_EDGE_PX)
        }
        if (endX <= startX) return null
        return SlideCoordinates(startX, startY, endX, startY)
    }

    private data class SlideCoordinates(
        val startX: Float,
        val startY: Float,
        val endX: Float,
        val endY: Float,
    )

    companion object {
        private const val TAG = "CaptchaSlide"
        private const val SLIDE_TEXT_XPATH = "//TextView[contains(@text,'向右滑动验证')]"
        private const val START_OFFSET_PX = 25f
        private const val END_MARGIN_PX = 20f
        private const val SCREEN_EDGE_PX = 50f
        private const val MIN_DISTANCE_RATIO = 1.5f
        private const val SETTLE_DELAY_MS = 500L
        private const val POST_SLIDE_DELAY_MS = 2000L
        private const val DURATION_MIN_MS = 500L
        private const val DURATION_MAX_MS = 600L

        private val mutex = Mutex()
    }
}
