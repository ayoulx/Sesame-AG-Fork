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
    ├── 60_orchard_chou.py
    ├── 70_forest_read.py
    ├── 80_golden_bean_mall.py
    ├── 90_patrol.py
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

### 农场抽抽乐（`fork:orchardchou`）

0.2.6 的 `OrchardChouChouLe` 任务流原样搬过来，补 6 个 RPC（`enterDrawActivity` /
`listDrawTasks` / `finishDrawTask` / `receiveDrawTaskAward` / `syncDrawBalance` / `batchDraw`）。
活动状态存 `UserDataStore`，结束时间到点即停；上一轮结束后每天最多重新探测一次，
探测权交给每日标识，避免本地残留的关闭状态把后续活动永久挡住。
0.2.6 里的 `continueCurrentRoundOnRetryableFailure` 重试开关在 0.1.9 的引擎上不存在，去掉。

### 无纸阅读（`fork:forestread`）

0.2.6 的 `ForestRead` + `ForestReadRpcCall`。每章本地计六分钟再上报实际阅读秒数，
上报结果未知时保留 `SUBMITTED` 状态只回查收益、不重放请求；跨章节靠持久化调度续接，
在 `ScheduledTaskRouter` 里注册 `forest_read` 子任务类型。

改写点：会话断言用 `AccountSessionCoordinator` 快照替代 `RpcDailyCircuit`；
续接计划查重用 `PersistentScheduleRegistry.list()`（0.1.9 没有 `listFresh()`）；
`UserDataStore.put` 无 `requirePersistence` 重载；去掉 0.2.x 的模块自建 HTTP 流量录制。

### 金豆商城兑换（`fork:goldenbeanmall`）

0.2.6 把金豆夺宝重写成独立模块并把集市抽成断点续抓会话。这里只取「商城兑换」这一个
可感知的新玩法：候选列表按同样口径翻页后落 `ExchangeOptionsCache`，设置页刷新走原广播桥。

兑换保留原判定：实付、外部下单、权益领取方式不明的商品只提醒不执行；下单前查金豆罐余额；
提交后在订单列表里比对「提交后新增且提交前不存在」的同一个 `orderNo` 才算成立，
否则保留待确认状态、不重复提交；每日次数按商品规格计数。

### 保护地巡护（`fork:patrol`）

0.2.6 的 `task/antForestPatrol` 四个文件整套搬入，独立成「保护地巡护」模块：
新版地图推进、骰子、事件、满星切图，以及动物伙伴的能量领取与自动派遣。

改写点：`Log.forestPatrol` 频道不存在，统一写森林频道；`AccountSessionCheck` 的
`Boolean` 判定改写为 `isCurrentSession`；`TaskFlowExecutionState` 与引擎的 `executionState`
参数不存在，去掉；`ModelGroup` 补 `FOREST_PATROL` 分组，`ModelOrder` 补注册。

保护证书兑换依赖 0.2.6 重写过的 `Reserve.exchangeTree`（带目标数、保留能量、待确认订单回查）。
这里给 0.1.9 的保护地模块新增一个 `exchangeCertificateOnce`：只在服务端明确可申请、
且兑换后能量不低于保留值时申请一张，语义对齐、不引入 0.2.x 的订单确认链路。
旧版巡护与碎片合成在 0.1.9 的森林页已有等价实现，这两个开关默认关闭，避免同账号重复巡护。

## 没有搬的部分

游戏中心（`task/common/GameCenterPlayRpcCall`）不是独立开关，而是 0.2.6 对
`AntDodo` / `FarmGame` / `AntForest` 等模块「游戏化任务」判定逻辑的统一重构，
它依赖 0.2.x 的 `RpcDailyCircuit` 与 `SerialTaskQueue`。搬它等于改这些模块的任务动作判定，
与「只加功能不动既有行为」的目标冲突，所以留空。

金豆夺宝的芝麻粒换豆（`goldenBeanSesameExchangeDailyBeanAmount`）需要 0.2.6 里
多入口的 `GoldenBeanRpcCall.index(entry)`，属于同一模块的第二个入口，暂未纳入。

要加新功能时，照着 `40_forest_dress.py` 的样子来：payload 放全文，锚点改上游文件，`verify.sh --build` 过了再提交。
