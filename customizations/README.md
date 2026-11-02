# customizations

上游代码一行不改。所有改动都在这里，构建前由 `apply.sh` 打到工作区，`verify.sh` 负责证明它打得对。

基线固定在上游 tag `4204-0.1.9`。0.2.0 起上游改了两处行为，这个分支不接受：

- 账号槽位限制（`AccountSlotRegistry` 一类的账号可用性判定）；
- 宿主必须先进模块 App 才能跑任务（存储改成跨进程 `bindService`，模块未启动时处于 stopped state）。

所以这里走的是「留在 0.1.9 的存储与会话模型，把 0.2.6 里能独立成立的功能搬过来」的路子。

## 目录

```
customizations/
├── apply.sh          按文件名顺序执行 patches/*.py
├── verify.sh         还原基线 → 打补丁 → 再打一遍 → 断言
├── patchkit.py       锚点定位、幂等标记、行尾无损
├── checks.py         verify.sh 用到的结构断言
└── patches/
    ├── 10_module_switches.py
    ├── 20_captcha_solver.py
    ├── 30_tool_settings.py
    ├── 40_forest_dress.py
    ├── 50_build_config.py
    └── payload/      新增文件的全文，由补丁落盘
```

## 补丁规则

1. **唯一原文定位**：锚点在目标文件里必须恰好出现 1 次，命中 0 次或多次都直接失败，不做模糊匹配。
2. **幂等**：每处改动都带 `[fork:<tag>:<name>]` 标记，已存在就跳过；同一标记重复出现会被 `verify.sh` 判为失败。
3. **行尾无损**：读写按文件自身行尾还原。上游文件是 LF 就写 LF，是 CRLF 就写 CRLF。
4. **只动声明过的文件**：`verify.sh` 拿 `git status` 和补丁自报的 touched 清单对账，多改一个文件就报错。
5. **不留占位**：`TODO` / `FIXME` 出现在新增行里直接失败。

## 用法

```bash
bash customizations/apply.sh          # 打补丁
bash customizations/verify.sh         # 自检（会先还原基线再重打，可反复跑）
bash customizations/verify.sh --build # 自检 + 编译
```

## 已移植

### 滑块验证（`fork:captcha`）

从 [Fansirsqi-Sesame-TK](https://github.com/Fansirsqi/Sesame-TK) 的 `hook/BaseCaptchaHandler` + `hook/simple/*` 移植，落在 `hook/captcha/`：

- `SimplePageManager`：只挂 `Application.dispatchActivityResumed` 与验证码弹窗的 `show()`，拿顶层 Activity 与弹窗视图；
- `SlideCaptchaHandler`：找「向右滑动验证」文本 → 定位滑块 → 换算屏幕坐标 → 合成滑动 → 复查文本消失；
- `MotionEventSimulator`：1 次 DOWN + 15 次 MOVE + 1 次 UP，带抖动与真实间隔；
- `SimpleXpathParser` / `SimpleViewImage` / `ViewHierarchyAnalyzer`：够用即可的视图查询与遍历。

相对参考实现去掉的部分，都是它自己也没在用的路径：全量 `Dialog` 构造监听（改为只挂验证码弹窗类）、`input swipe` shell 兜底（需要 root/服务，且与 MotionEvent 重复）、阻断 `show()` 的 UI 层拦截（弹窗被拦住就没有可滑的界面，和滑动逻辑自相矛盾）。

门禁三道：

1. 设置里手动打开（`ModuleSwitches.isCaptchaSolverEnabled`，默认关闭）——开关存在 `Files.CONFIG_DIR/module_switches.json`，模块进程写、宿主进程读，不依赖框架的 remote preferences，也不要求先开模块 App；
2. 目标应用版本 ≤ `10.6.58.99999`（`CaptchaSolver.isSupported`）；
3. 目标 Activity 属于已验证的白名单（`XRiverActivity` / `AlipayLogin`）。

开关在「设置 → 工具」里，关掉即时生效，打开需要重启目标应用（挂钩发生在进程启动阶段）。

### 每日随机换装（`fork:forestdress`）

0.2.6 的 `ForestDress` 原样搬过来，配两个上游没有的 RPC（`listUserDressForBackpack` / `wearDress`），开关在「蚂蚁森林 → 每日随机更换森林装扮」，默认关闭。

### 构建配置（`fork:build`）

- ABI：默认只出 `arm64-v8a`；`-PforkAbis=all` 出全 ABI，`-PforkAbis=arm64-v8a,x86_64` 出指定组合。
- 签名：固定密钥 `keystore/fork-release.p12`（PKCS12，配置见 `keystore/fork-release.properties`），升级不换签名。
- 体积：`packaging.dex.useLegacyPackaging = true`，dex 走压缩打包。

## 没有搬的部分

0.2.6 的其余新功能（保护地巡护、金豆夺宝、无纸阅读、抽抽乐、游戏中心等）都建立在 0.2.x 重写过的存储层（`StoreAccess`/`UserDataStore`）、会话层（`AccountSessionCheck` 含槽位判定）、调度层（`PersistentScheduleKind.MODULE_CHILD`）之上。整包对拷等于把上面两条限制一起搬进来，与这个分支的前提冲突；拆开搬则需要逐个改写这些依赖，属于独立工作量，按功能单独立补丁更稳妥。

要加新功能时，照着 `40_forest_dress.py` 的样子来：payload 放全文，锚点改上游文件，`verify.sh --build` 过了再提交。
