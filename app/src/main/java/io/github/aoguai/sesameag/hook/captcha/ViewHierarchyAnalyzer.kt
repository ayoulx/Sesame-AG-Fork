package io.github.aoguai.sesameag.hook.captcha

import android.view.View
import android.view.ViewGroup
import android.widget.ImageView
import io.github.aoguai.sesameag.util.Log

/**
 * 从「向右滑动验证」文本节点出发，找到真正可拖动的滑块视图。
 *
 * 目标应用的滑块组件里，可拖动的是包围图标 [ImageView] 的那层容器，
 * 所以从文本节点的父容器开始向下找第一个可见 ImageView，取它的父视图。
 */
object ViewHierarchyAnalyzer {

    private const val TAG = "CaptchaViews"

    fun findActualSliderView(slideTextView: SimpleViewImage): View? {
        val container = slideTextView.originView.parent as? ViewGroup ?: return null
        val slider = findSliderInGroup(container)
        if (slider == null) {
            Log.error(TAG, "未找到可拖动滑块视图")
            return null
        }
        val location = IntArray(2).also { slider.getLocationOnScreen(it) }
        Log.record(TAG, "滑块 ${slider.javaClass.simpleName} 位置=[${location[0]},${location[1]}] 尺寸=${slider.width}x${slider.height}")
        return slider
    }

    private fun findSliderInGroup(group: ViewGroup): View? {
        for (i in 0 until group.childCount) {
            val child = group.getChildAt(i)
            if (child is ImageView && child.isShown) {
                return child.parent as? View
            }
            if (child is ViewGroup) {
                findSliderInGroup(child)?.let { return it }
            }
        }
        return null
    }
}
