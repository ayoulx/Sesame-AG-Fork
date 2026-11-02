package io.github.aoguai.sesameag.hook.captcha

import android.view.View
import android.view.ViewGroup
import android.widget.TextView

/**
 * 对 [View] 的精简包装：只提供滑块判定需要的文本、坐标与子节点遍历。
 * 子节点结果按需缓存，避免同一轮 XPath 查询里重复构造。
 */
class SimpleViewImage(val originView: View) {

    private var children: Array<SimpleViewImage?>? = null

    fun getText(): String? =
        if (originView is TextView) {
            originView.text?.toString()
        } else {
            originView.contentDescription?.toString()
        }

    fun locationOnScreen(): IntArray {
        val location = IntArray(2)
        originView.getLocationOnScreen(location)
        return location
    }

    fun childCount(): Int = if (originView is ViewGroup) originView.childCount else 0

    fun childAt(index: Int): SimpleViewImage {
        val childCount = childCount()
        require(index in 0 until childCount) { "子节点越界: $index / $childCount" }
        val cache = children ?: arrayOfNulls<SimpleViewImage>(childCount).also { children = it }
        cache[index]?.let { return it }
        val viewGroup = originView as ViewGroup
        val wrapped = SimpleViewImage(viewGroup.getChildAt(index))
        cache[index] = wrapped
        return wrapped
    }

    fun children(): List<SimpleViewImage> {
        val count = childCount()
        if (count <= 0) return emptyList()
        val result = ArrayList<SimpleViewImage>(count)
        for (i in 0 until count) {
            result.add(childAt(i))
        }
        return result
    }

    fun type(): String = originView.javaClass.simpleName

    fun attribute(key: String): Any? =
        when (key) {
            ATTR_TEXT -> getText()
            ATTR_CONTENT_DESCRIPTION -> originView.contentDescription?.toString()
            else -> null
        }

    companion object {
        const val ATTR_TEXT = "text"
        const val ATTR_CONTENT_DESCRIPTION = "contentDescription"
    }
}
