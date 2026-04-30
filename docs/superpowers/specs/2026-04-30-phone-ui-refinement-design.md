# 手机APP UI精炼设计 — 极简竞技风格

> 状态: 设计阶段 | 日期: 2026-04-30

## 1. 设计方向

**极简竞技** — 深黑底色 + 高对比白字 + 琥珀金强调。体育馆记分牌风格。

## 2. 配色方案 (Design Tokens)

| 角色 | 色值 | 用途 |
|------|------|------|
| `bg_primary` | `#080808` | 主背景 |
| `bg_card` | `#0D0D0D` | 卡片/面板背景 |
| `bg_surface` | `#111111` | 次级表面 |
| `accent` | `#FFC107` | 琥珀金强调 |
| `accent_dim` | `#C8A000` | 暗琥珀 |
| `accent_light` | `#FFE082` | 浅琥珀 |
| `border_subtle` | `#1A1A1A` | 细边框 |
| `border_medium` | `#222222` | 中边框 |
| `border_strong` | `#2A2A2A` | 粗边框 |
| `text_primary` | `#FFFFFF` | 主文字 |
| `text_secondary` | `#888888` | 次文字 |
| `text_tertiary` | `#666666` | 辅助文字 |
| `text_dim` | `#555555` | 弱化文字 |
| `error` | `#FF1744` | 错误/犯规 |
| `success` | `#00E676` | 成功 |

## 3. 组件风格

- 卡片/按钮: 2px 圆角
- 数字: monospace 粗体 (fontWeight 900)
- 标签: 11sp + letterSpacing 0.08 + 大写
- 分隔装饰: 金色渐变线 / 左侧3px强调条
- 边框: 1px solid
- 主按钮: 金色实心 + 黑字
- 次按钮: 透明 + 灰色边框

## 4. 组件架构

```
MainActivity (Tab容器, 持有WebSocketClient)
├── Tab 1: HomeFragment
├── Tab 2: InProgressFragment
│         ├── MatchView    (比赛进行中)
│         └── TrainingView (训练/闯关进行中)
└── Tab 3: SettingsFragment
```

Tab 2 用单一 Fragment + 内部 View 切换（比赛/训练不会同时进行）。

## 5. 新增/修改文件清单

| 文件 | 操作 | 说明 |
|------|------|------|
| `res/values/colors.xml` | 新建 | 配色Token |
| `res/values/strings.xml` | 新建 | 字符串资源 |
| `res/values/styles.xml` | 重写 | 统一样式 |
| `res/drawable/btn_primary_bg.xml` | 新建 | 金色按钮背景 |
| `res/drawable/btn_secondary_bg.xml` | 新建 | 透明边框按钮背景 |
| `res/drawable/card_bg.xml` | 新建 | 卡片背景 |
| `res/drawable/divider_gold.xml` | 新建 | 金色渐变分割线 |
| `res/layout/fragment_home.xml` | 重写 | 主页布局 |
| `res/layout/fragment_progress.xml` | 重写 | 进行中容器布局 |
| `res/layout/fragment_settings.xml` | 重写 | 设置布局 |
| `res/layout/view_match.xml` | 新建 | 比赛进行中内容 |
| `res/layout/view_training.xml` | 新建 | 训练进行中内容 |
| `res/layout/dialog_player_names.xml` | 新建 | 比赛选手姓名对话框 |
| `res/layout/dialog_level_select.xml` | 新建 | 训练关卡选择对话框 |
| `InProgressFragment.java` | 重写 | 根据模式切换View |
| `HomeFragment.java` | 重写 | 套用新样式+对话框 |
| `SettingsFragment.java` | 重写 | 套用新样式+预览开关 |
| `WebSocketClient.java` | 新建 | WebSocket连接+消息分发 |
| `MainActivity.java` | 修改 | 集成WebSocket，Fragment复用 |

## 6. 界面设计

### 6.1 主页 Tab (HomeFragment)

- 顶栏：标题 "POOL·AR" + 连接状态指示(绿点+已连接/红点+已断开)
- 启动/停止按钮：金色主按钮 + 透明次按钮
- 三个模式卡片：比赛模式/训练模式/闯关模式
- 系统信息卡片：服务器地址、摄像头状态、当前模式
- 交互：比赛弹出姓名对话框、训练弹出关卡选择、闯关直接进入

### 6.2 进行中 Tab - 比赛 (MatchView)

- 双人选手卡片：姓名、比分大字(monospace 900)、球色归属
- 当前击球手：左侧金色强调条 + 金色三角箭头
- 球状态面板：1-15号球圆形网格，在台=亮白，进袋=灰+删除线
- 剩余统计行：纯色剩X颗·花色剩X颗·黑8在台/已进
- 交换击球按钮：带确认对话框

### 6.3 进行中 Tab - 训练 (TrainingView)

- 顶栏：返回选关箭头 + 档位名称
- 训练进度：第X题/共X题 + 金色进度条
- 摆球要求卡片：白球/目标球/目标袋位置 + 杆法提示
- 摆球验证区域：实时显示验证结果(正确/偏差方向)
- 推荐击球卡片：杆法、力度、走位信息
- 击球结果区域：等待中/成功/失败 三态切换
- 闯关进度：连续成功🔥计数 + 本关最高 + 总进度

### 6.4 设置 Tab (SettingsFragment)

- 服务器配置：IP/端口输入框 + 自动发现 + 保存重连
- 预览开关：摄像头预览/投影预览 各带Toggle开关
- 校准：状态显示 + 开始/停止按钮
- AI模型：已采集杆数 + 模型状态 + AI训练/重置按钮
- 默认选手姓名：选手一/选手二 输入框
- 底部：版本号 + 当前服务器信息

## 7. WebSocket 消息

| 消息类型 | 方向 | 处理者 |
|----------|------|--------|
| `table_state` | 后端→APP | InProgressFragment |
| `score_update` | 后端→APP | InProgressFragment (MatchView) |
| `pocket_event` | 后端→APP | InProgressFragment (MatchView) |
| `shot_result` | 后端→APP | InProgressFragment (TrainingView) |
| `drill_info` | 后端→APP | InProgressFragment (TrainingView) |
| `placement_result` | 后端→APP | InProgressFragment (TrainingView) |

WebSocketClient 采用观察者模式，MainActivity持有实例，Fragment注册回调。

## 8. 交互规则

- 点击模式卡片后自动切到Tab 2（进行中）
- 击球结果由后端自动判定推送，用户不需操作手机
- 交换击球按钮需确认对话框防误触
- 预览WebSocket流按需开启/关闭，不常驻
- 设置项即时保存到SharedPreferences
