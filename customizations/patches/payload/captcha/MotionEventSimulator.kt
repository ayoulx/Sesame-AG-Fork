package io.github.aoguai.sesameag.hook.captcha

import android.os.SystemClock
import android.view.MotionEvent
import android.view.View
import io.github.aoguai.sesameag.util.Log
import kotlinx.coroutines.delay
import kotlin.random.Random

/**
 * 在目标视图上合成一次人手滑动：1 次 DOWN + [STEPS] 次 MOVE + 1 次 UP。
 *
 * 轨迹采用均匀步进叠加小幅抖动，MOVE 之间插入真实延迟，
 * 避免出现「瞬时瞬移」这种一眼假的触摸序列。
 */
object MotionEventSimulator {

    private const val TAG = "CaptchaSwipe"
    private const val STEPS = 15

    suspend fun swipe(view: View, startX: Float, startY: Float, endX: Float, endY: Float, durationMs: Long) {
        if (!view.isShown || !view.isEnabled) {
            Log.error(TAG, "滑块不可见或未启用，跳过滑动")
            return
        }
        val downTime = SystemClock.uptimeMillis()
        dispatch(view, MotionEvent.ACTION_DOWN, startX, startY, downTime, downTime)
        delay(Random.nextLong(30, 80))

        val stepDuration = ((durationMs - 100) / STEPS).coerceAtLeast(1L)
        val xStep = (endX - startX) / STEPS
        val yStep = (endY - startY) / STEPS
        for (i in 1..STEPS) {
            val x = startX + xStep * i + Random.nextInt(-3, 4)
            val y = startY + yStep * i + Random.nextInt(-2, 3)
            dispatch(view, MotionEvent.ACTION_MOVE, x, y, downTime, downTime + stepDuration * i)
            delay(stepDuration)
        }

        dispatch(view, MotionEvent.ACTION_UP, endX, endY, downTime, downTime + durationMs)
    }

    private fun dispatch(view: View, action: Int, x: Float, y: Float, downTime: Long, eventTime: Long) {
        val properties =
            arrayOf(
                MotionEvent.PointerProperties().apply {
                    id = 0
                    toolType = MotionEvent.TOOL_TYPE_FINGER
                },
            )
        val coords =
            arrayOf(
                MotionEvent.PointerCoords().apply {
                    this.x = x
                    this.y = y
                    pressure = 1f
                    size = 1f
                },
            )
        val event = MotionEvent.obtain(downTime, eventTime, action, 1, properties, coords, 0, 0, 1f, 1f, 0, 0, 0, 0)
        try {
            view.dispatchTouchEvent(event)
        } finally {
            event.recycle()
        }
    }
}
