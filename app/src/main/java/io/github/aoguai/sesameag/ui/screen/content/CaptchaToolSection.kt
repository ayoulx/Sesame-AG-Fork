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
            subtitle = "目标应用 ≤ ${CaptchaSolver.MAX_SUPPORTED_VERSION} 可用；自动完成「向右滑动」验证，默认关闭，开关后立即生效，不必重启目标应用",
            icon = Icons.Rounded.Gesture,
            checked = enabled,
            onCheckedChange = { value ->
                val written = ModuleSwitches.setCaptchaSolverEnabled(value)
                enabled = written
                val message =
                    when {
                        !written -> "保存失败，请检查存储权限"
                        value -> "已开启，下一处验证码即生效"
                        else -> "已关闭"
                    }
                Toast.makeText(context, message, Toast.LENGTH_SHORT).show()
            },
        )
    }

    item {
        Text(
            text = "运行环境：靠 LSPosed 在宿主进程内直接派发触摸事件，不执行 root 命令、不需要 Shizuku、也不需要无障碍服务（模块本身仍要求 LSPosed / root 环境）。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline,
        )
    }

    item {
        Text(
            text = "排查：在「日志 - 全部日志」里搜「滑块」，能看到启动时的开关状态、开关文件位置，以及每次命中验证码的结果。页面改版或风控策略调整后可能失效；不开也能正常完成任务。",
            style = MaterialTheme.typography.bodySmall,
            color = MaterialTheme.colorScheme.outline,
        )
    }
}
