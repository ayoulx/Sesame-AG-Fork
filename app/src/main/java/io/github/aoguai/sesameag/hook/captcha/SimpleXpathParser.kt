package io.github.aoguai.sesameag.hook.captcha

import java.util.regex.Pattern

/**
 * 仅覆盖滑块验证用得到的三种 XPath 形态：
 *
 * - `//TextView[contains(@text,'向右滑动验证')]`
 * - `//TextView[@text='向右滑动验证']`
 * - `//TextView`
 *
 * 不追求通用性，避免引入完整 XPath 解析器的体积与不确定性。
 */
object SimpleXpathParser {

    private val CONTAINS_PATTERN =
        Pattern.compile("//([\\w.]+)\\[contains\\(@(\\w+),'([^']*)'\\)]", Pattern.CASE_INSENSITIVE)

    private val EQUALS_PATTERN =
        Pattern.compile("//([\\w.]+)\\[@(\\w+)='([^']*)']", Pattern.CASE_INSENSITIVE)

    private val TAG_PATTERN = Pattern.compile("//([\\w.]+)", Pattern.CASE_INSENSITIVE)

    fun evaluate(root: SimpleViewImage, xpath: String): List<SimpleViewImage> {
        CONTAINS_PATTERN.matcher(xpath).takeIf { it.find() }?.let { matcher ->
            return collect(root, matcher.group(1), matcher.group(2), matcher.group(3), true)
        }
        EQUALS_PATTERN.matcher(xpath).takeIf { it.find() }?.let { matcher ->
            return collect(root, matcher.group(1), matcher.group(2), matcher.group(3), false)
        }
        TAG_PATTERN.matcher(xpath).takeIf { it.find() }?.let { matcher ->
            return collect(root, matcher.group(1), null, null, false)
        }
        return emptyList()
    }

    private fun collect(
        root: SimpleViewImage,
        className: String,
        attrName: String?,
        attrValue: String?,
        contains: Boolean,
    ): List<SimpleViewImage> {
        val results = ArrayList<SimpleViewImage>()
        walk(root, className, attrName, attrValue, contains, results)
        return results
    }

    private fun walk(
        node: SimpleViewImage,
        className: String,
        attrName: String?,
        attrValue: String?,
        contains: Boolean,
        results: MutableList<SimpleViewImage>,
    ) {
        val typeMatches = className == "*" || node.type() == className
        if (typeMatches) {
            if (attrName == null) {
                results.add(node)
            } else {
                val actual = node.attribute(attrName)?.toString()
                if (actual != null && (if (contains) actual.contains(attrValue.orEmpty()) else actual == attrValue)) {
                    results.add(node)
                }
            }
        }
        for (child in node.children()) {
            walk(child, className, attrName, attrValue, contains, results)
        }
    }
}
