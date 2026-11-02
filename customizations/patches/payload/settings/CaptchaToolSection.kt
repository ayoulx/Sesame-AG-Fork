package io.github.aoguai.sesameag.ui.screen.content

import SettingsSwitchItem
import android.widget.Toast
import androidx.compose.foundation.lazy.LazyListScope
import androidx.compose.material.icons.Icons
import androidx.compose.material.icons.rounded.Gesture
import androidx.compose.material3.MaterialTheme
import androidx.compose.material3.Text
import androidx.compose.runtime.getValue
import androidx.compose.runtime.mutableStateOf
import androidx.compose.runtime.remember
import androidx.compose.runtime.setValue
import androidx.compose.ui.platform.LocalContext
import io.github.aoguai.sesameag.hook.captcha.CaptchaSolver
import io.github.aoguai.sesameag.util.ModuleSwitches

/**
 * 设置页「工具」分组的条目。
 *
 * 单独成文件，补丁只需在设置页里插一行 `captchaToolSection()`，
 * 不必改动上游的排版与状态管理代码。
 */
fun LazyListScope.captchaToolSection() {
    item {
        Text(
            text = "工具",
            style = MaterialTheme.typography.labelLarge,
            color = MaterialTheme.colorScheme.primary,
        )
    }

    item {
        val context = LocalContext.current
        var enabled by remember { mutableStateOf(ModuleSwitches.isCaptchaSolverEnabled()) }
        SettingsSwitchItem(
            title = "自动过滑块验证",
            subtitle = "目标应用 ≤ ${CaptchaSolver.MAX_SUPPORTED_VERSION} 可用；开启后自动完成「向右滑动」验证，默认关闭，重启目标应用后生效",
            icon = Icons.Rounded.Gesture,
            checked = enabled,
            onCheckedChange = { value ->
                val written = ModuleSwitches.setCaptchaSolverEnabled(value)
                enabled = written
                val message =
                    when {
                        !written -> "保存失败，请检查存储权限"
                        value -> "已开启，重启目标应用后生效"
                        else -> "已关闭"
                    }
                Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
            },
        )
    }

    item {
        Text(
            text = "滑块验证依赖界面自动化，页面改版或风控策略调整后可能失效；不开也能正常完成任务。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline,
        )
    }
}
