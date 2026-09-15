# WebBuilder 设计器控件清单（控件注册表）
> 数据来源：工程的 **`wb/system/controls.json`**（设计器自己的控件注册表，133 个控件）+ 全项目 **2777 个 `.xwl`** 的实际使用统计。
>
> 这份表回答四个问题：**有哪些控件 / 各自干什么 / 该挂在哪里 / 哪种情况用哪个**。
> 查单个控件的合法字段用 `xwl.py schema <控件id> --controls <…/controls.json>`。

## 一、怎么读这份表
| 字段 | 含义 |
|---|---|
| `id` | 控件 id，就是 xwl 里的 `"type"` 值；也是设计器面板里的名字 |
| ExtJS 类型 | `general.type`，运行时真正实例化的类 |
| 库 | `general.tag.lib`：**1=桌面 ExtJS**、**2=移动 Touch（`t` 前缀）**、**3=原生 HTML**；空=结构/服务端伪控件 |
| 容器 | `general.container` 为 true → **可以挂子控件**；其余挂子控件没有意义 |
| 面板 | 是否出现在设计器左侧控件面板（`general.design !== false`）。标 `—` 的是**内部控件**，不能在面板里拖，只能由设计器自动生成或手写 |
| autoNames | `general.autoNames`：作为子控件时的**自动 itemId**（按父控件 `type` 取名，`any` 为兜底）。见第四节 |

## 二、三套控件库，先选库再选控件
| 库 | 数量 | 说明 |
|---|---|---|
| 桌面 ExtJS（lib=1） | 58 | PC 页面默认用这套。容器类（panel/form/tab/window…）+ 表单字段 + grid/tree + 图表 |
| 移动 Touch（lib=2） | 39 | `t` 前缀；**同一工程的移动端页面另一套**。命名与桌面一一对应（`panel`↔`tpanel`、`grid`↔`tgrid`、`text`↔`ttext`…） |
| 原生 HTML（lib=3） | 18 | `div/span/a/p/ul/li/input/header/hr/br` 等，用于自由排版；`supcan` 系（`treelist`/`report`）也在这组 |
| 结构 / 服务端（无 lib） | 18 | `module`/`folder`（树结构）、`store`/`dataprovider`/`serverscript`/`method`/`xwl`/`response`/`column`/`feature`/`array`… **不是可见控件**，是配置载体（见第五节） |

## 三、控件总表（按设计器面板分组）

### (根)
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `module` | — | 结构/服务端 |  | ✔ | 2777 | **每个 xwl 的根节点**（页面钥匙）。顶层 `title`/`roles`/`inframe`/`pageLink` 是它的属性；`serverScript` 挂在这层 |

### General
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `viewport` | Ext.container.Viewport | 桌面 | ✔ | ✔ | 570 | 全屏根容器（浏览器视口）。PC 页面的最外层，通常再放 panel/grid |
| `folder` | — | 结构/服务端 |  | — | 3 | 树上的分组节点，不渲染。只用于把多个对象归到一组 |
| `panel` | Ext.panel.Panel | 桌面 | ✔ | ✔ | 1800 | 最通用的面板/容器。放表单、网格、工具栏都行 |
| `window` | Ext.window.Window | 桌面 | ✔ | ✔ | 1064 | 弹窗。新增/编辑/选择类交互的载体 |
| `form` | Ext.form.Panel | 桌面 | ✔ | ✔ | 153 | 表单面板。比 panel 多出表单提交/校验语义，`Wb.upload` 的 `form` 参数要指这里 |
| `tab` | Ext.tab.Panel | 桌面 | ✔ | ✔ | 165 | 页签容器，子节点通常是多个 panel |
| `fieldset` | Ext.form.FieldSet | 桌面 | ✔ | ✔ | 122 | 带标题的分组框，用来给表单分区 |
| `container` | Ext.container.Container | 桌面 | ✔ | ✔ | 36 | 裸容器（无边框无标题），做布局分组用 |
| `comp` | Ext.Component | 桌面 |  | ✔ | 11 | 通用组件占位，需要手写配置时用 |
| `toolbar` | Ext.toolbar.Toolbar | 桌面 | ✔ | ✔ | 1492 | 工具栏。**查询条的标准载体**（`out: app.tbar` 收它里面的控件值） |
| `menu` | Ext.menu.Menu | 桌面 | ✔ | — | 17 | 弹出菜单（内部控件，随按钮的 `menu` 配置生成） |
| `item` | — | 桌面 | ✔ | ✔ | 5434 | 工具栏项：分隔符（`-`）、占位（` `）、菜单项或任意控件的包装 |
| `button` | Ext.button.Button | 桌面 | ✔ | ✔ | 974 | 按钮。事件写在 `events.click` |
| `hidden` | Ext.form.field.Hidden | 桌面 |  | — | 35 | 隐藏字段：用来**传递不出现在界面上的参数**（内部控件，`out:` 照样会收集它） |
| `label` | Ext.form.Label | 桌面 |  | ✔ | 311 | 纯文本标签 |
| `text` | Ext.form.field.Text | 桌面 |  | ✔ | 5700 | 单行文本输入 |
| `number` | Ext.form.field.Number | 桌面 |  | ✔ | 2015 | 数字输入（空值会被 `out:` 转成 `"0"`，注意） |
| `textarea` | Ext.form.field.TextArea | 桌面 |  | ✔ | 374 | 多行文本。长备注、SQL 片段展示 |
| `combo` | Ext.form.field.ComboBox | 桌面 |  | ✔ | 5033 | 下拉框。常带一个 `store` 子节点作为候选项来源 |
| `date` | Ext.form.field.Date | 桌面 |  | ✔ | 1200 | 日期选择（`datefield`） |
| `month` | Ext.ux.form.MonthField | 桌面 |  | ✔ | 105 | 月份选择（`Ext.ux.form.MonthField`） |
| `time` | Ext.form.field.Time | 桌面 |  | ✔ | 1 | 时间选择 |
| `datetime` | Ext.form.field.Datetime | 桌面 |  | ✔ | 277 | 日期+时间（设计器里用 combo 形态渲染） |
| `file` | Ext.form.field.File | 桌面 |  | ✔ | 155 | 文件上传字段。配合 `Wb.upload` 使用，`out:` 会额外带 `$<itemId>` |
| `check` | Ext.form.field.Checkbox | 桌面 |  | ✔ | 582 | 单个复选框 |
| `radio` | Ext.form.field.Radio | 桌面 |  | ✔ | 107 | 单选框（要成组时用 `radiogroup`） |
| `array` | Array | 结构/服务端 | ✔ | — | 1886 | **配置载体**：承载数组型配置项，`itemId` 就是配置项名（`columns`/`features`/`dockedItems`…） |
| `clientscript` | — | 结构/服务端 |  | — | 2 | 页面级客户端脚本块（内部控件） |

### List View
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `dataview` | Ext.view.View | 桌面 |  | ✔ | 4 | 自定义数据视图（模板渲染） |
| `grid` | Ext.grid.Panel | 桌面 |  | ✔ | 1320 | 表格（`Ext.grid.Panel`）。**最常见的业务主控件** |
| `tree` | Ext.tree.Panel | 桌面 |  | ✔ | 43 | 树（`treepanel`） |
| `propertygrid` | Ext.grid.property.Grid | 桌面 |  | ✔ |  | 属性网格（左属性名右值） |
| `column` | — | 桌面 | ✔ | — | 20765 | **表格列定义**。`itemId`=字段名；可嵌套 `column` 做分组表头；可挂 `combo`/`number`/`text` 作单元格编辑器 |
| `tableview` | — | 桌面 |  | ✔ | 193 | **配置载体**：`viewConfig` 视图配置 |
| `feature` | — | 桌面 |  | — | 434 | **配置载体**：`features` grid 特性（可编辑、行号等） |
| `editing` | — | 桌面 |  | — |  | **配置载体**：`plugins` 编辑插件（行内编辑） |

### Data Access
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `store` | Ext.data.Store | 结构/服务端 |  | — | 2021 | 数据源（`Ext.data.Store`）。`configs.url='m?xwl=…'` 指向 SQL 文件；也可挂在 combo 下做候选项 |
| `treestore` | Ext.data.TreeStore | 结构/服务端 |  | — | 44 | 树数据源 |
| `socket` | Ext.data.Socket | 结构/服务端 |  | — |  | WebSocket 数据源（内部） |
| `datamodel` | — | 结构/服务端 |  | — |  | 数据模型定义（内部） |
| `dataprovider` | — | 结构/服务端 |  | — | 1143 | **SQL 执行器**：`configs.sql` / `totalSql` 放 SQL，`{?名?}` 是绑定参数 |
| `query` | — | 结构/服务端 |  | — | 595 | 查询控件：直接给 SQL 并输出（内部） |
| `updater` | — | 结构/服务端 |  | — | 19 | 更新控件：执行写库（内部） |
| `sqlswitcher` | — | 结构/服务端 |  | — | 1 | SQL 分支切换（内部） |

### Server
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `serverscript` | — | 结构/服务端 |  | — | 2 | **服务端脚本容器**：`configs.serverScript` 里写 JS（`app.get`/`app.run`/`app.send`/`app.rundomain`）。写在 `module` 节点上 |
| `method` | — | 结构/服务端 |  | — | 43 | 动态调用服务端方法（内部） |
| `xwl` | xwl | 结构/服务端 |  | — | 36 | 在另一个 xwl 里运行 xwl（内部） |
| `response` | — | 结构/服务端 |  | — | 123 | 直接输出响应（内部） |
| `string` | — | 结构/服务端 |  | — | 30 | 服务端字符串资源（内部） |
| `mailer` | — | 结构/服务端 |  | — | 1 | 发邮件（内部） |

### Additional
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `image` | Ext.Img | 桌面 |  | ✔ | 87 | 图片显示（`Ext.Img`） |
| `fieldcontainer` | Ext.form.FieldContainer | 桌面 | ✔ | ✔ | 7 | 字段容器：把多个字段当一个表单项排 |
| `checkgroup` | Ext.form.CheckboxGroup | 桌面 | ✔ | ✔ |  | 复选框组 |
| `radiogroup` | Ext.form.RadioGroup | 桌面 | ✔ | ✔ | 33 | 单选框组 |
| `displayfield` | Ext.form.field.Display | 桌面 |  | ✔ |  | 只读展示字段（只显示不带输入框） |
| `htmleditor` | Ext.form.field.HtmlEditor | 桌面 |  | ✔ | 5 | 富文本编辑器 |
| `slider` | Ext.slider.Single | 桌面 |  | ✔ | 1 | 滑块（单值） |
| `buttongroup` | Ext.container.ButtonGroup | 桌面 | ✔ | ✔ | 5 | 按钮组 |
| `colorfield` | Wb.field.ColorField | 桌面 |  | ✔ |  | 颜色选择（`Wb.field.ColorField`） |
| `picker` | Ext.form.field.ControlPicker | 桌面 |  | ✔ | 30 | 通用选择器字段（`ControlPicker`） |

### Charts
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `echart` | Ext.echart.Chart | 桌面 |  | ✔ | 5 | ECharts 图表容器 |
| `eaxis` | — | 桌面 |  | — | 6 | ECharts 坐标轴配置（内部） |
| `eseries` | Ext.chart.series.Series | 桌面 |  | — | 8 | ECharts 系列配置（内部） |
| `etitle` | — | 桌面 |  | — | 2 | ECharts 标题（内部） |
| `elabel` | — | 桌面 |  | — | 3 | ECharts 标签（内部） |
| `etextstyle` | — | 桌面 |  | — | 3 | ECharts 文字样式（内部） |
| `elegend` | — | 桌面 |  | — | 3 | ECharts 图例（内部） |
| `etooltip` | — | 桌面 |  | — | 2 | ECharts 提示框（内部） |
| `egrid` | — | 桌面 |  | — |  | ECharts 网格（内部） |
| `etoolbox` | — | 桌面 |  | — | 1 | ECharts 工具箱（内部） |
| `chart` | Ext.chart.Chart | 桌面 |  | ✔ | 11 | ExtJS 原生图表 |
| `axis` | Ext.chart.axis.Axis | 桌面 |  | — | 21 | Ext 图表坐标轴（内部） |
| `series` | Ext.chart.series.Series | 桌面 |  | — | 16 | Ext 图表系列（内部） |
| `chartlabel` | Ext.chart.label.Label | 桌面 |  | — | 3 | Ext 图表标签（内部） |

### Touch
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `tviewport` | tviewport | 移动 | ✔ | — | 13 | 【移动】全屏根容器 |
| `tpanel` | Ext.Panel | 移动 | ✔ | — | 5 | 【移动】面板 |
| `tcontainer` | Ext.Container | 移动 | ✔ | — | 20 | 【移动】裸容器 |
| `tform` | Ext.form.Panel | 移动 | ✔ | — | 1 | 【移动】表单面板 |
| `ttab` | Ext.tab.Panel | 移动 | ✔ | — |  | 【移动】页签容器 |
| `tfieldset` | Ext.form.FieldSet | 移动 | ✔ | — | 4 | 【移动】分组框 |
| `ttoolbar` | Ext.Toolbar | 移动 | ✔ | — | 4 | 【移动】工具栏 |
| `ttitlebar` | Ext.TitleBar | 移动 | ✔ | — | 13 | 【移动】标题栏（相当于导航条） |
| `tmenu` | Ext.Menu | 移动 | ✔ | — |  | 【移动】弹出菜单（内部） |
| `tstore` | Ext.data.Store | 移动 |  | — | 13 | 【移动】数据源 |
| `ttreestore` | Ext.data.TreeStore | 移动 |  | — | 2 | 【移动】树数据源 |
| `tsocket` | Ext.data.Socket | 移动 |  | — |  | 【移动】WebSocket 数据源（内部） |
| `tcomp` | Ext.Component | 移动 |  | — | 3 | 【移动】通用组件占位 |
| `tspacer` | Ext.spacer | 移动 |  | — | 2 | 【移动】占位空白 |
| `tbutton` | Ext.Button | 移动 |  | — | 31 | 【移动】按钮 |
| `thidden` | Ext.field.Hidden | 移动 |  | — | 1 | 【移动】隐藏字段 |
| `tlabel` | Ext.Label | 移动 |  | — |  | 【移动】文本标签 |
| `ttext` | — | 移动 |  | — | 18 | 【移动】文本输入 |
| `tnumber` | Ext.field.Number | 移动 |  | — | 3 | 【移动】数字输入 |
| `tselect` | Ext.field.Select | 移动 |  | — | 5 | 【移动】下拉选择 |
| `tdate` | Ext.field.DatePicker | 移动 |  | — | 2 | 【移动】日期选择 |
| `tdatetime` | — | 移动 |  | — | 3 | 【移动】日期+时间 |
| `tfile` | Ext.field.File | 移动 |  | — | 1 | 【移动】文件字段 |
| `tcheck` | Ext.field.Checkbox | 移动 |  | — | 1 | 【移动】复选框 |
| `tradio` | Ext.field.Radio | 移动 |  | — | 9 | 【移动】单选框 |
| `tspinner` | Ext.field.Spinner | 移动 |  | — | 1 | 【移动】数字微调 |
| `tslider` | Ext.field.Slider | 移动 |  | — | 2 | 【移动】滑块 |
| `ttoggle` | Ext.field.Toggle | 移动 |  | — | 5 | 【移动】开关 |
| `timage` | Ext.Img | 移动 |  | — | 1 | 【移动】图片 |
| `tscroller` | — | 移动 |  | — |  | 【移动】滚动配置（内部） |

### Touch › List View
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `tdataview` | Ext.dataview.DataView | 移动 |  | — | 3 | 【移动】数据视图 |
| `tlist` | Ext.dataview.List | 移动 |  | — | 4 | 【移动】列表 |
| `tnlist` | Ext.dataview.NestedList | 移动 |  | — | 2 | 【移动】嵌套列表 |
| `tnavigate` | Ext.navigation.View | 移动 | ✔ | — | 1 | 【移动】导航视图（带返回栈） |
| `tgrid` | Ext.grid.Grid | 移动 |  | — | 2 | 【移动】网格 |
| `tcolumn` | — | 移动 | ✔ | — | 6 | 【移动】列定义（内部） |

### Touch › chart
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `tchart` | Ext.chart.CartesianChart | 移动 | ✔ | — | 3 | 【移动】图表 |
| `taxis` | Ext.chart.axis.Axis | 移动 |  | — | 7 | 【移动】图表坐标轴（内部） |
| `tseries` | Ext.chart.series.Series | 移动 |  | — | 4 | 【移动】图表系列（内部） |
| `tchartlabel` | Ext.chart.label.Label | 桌面 |  | — |  | 【移动】图表标签（内部） |

### Bootstrap
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `div` | div | 原生 |  | — | 21 | 【原生】块容器，做自由排版 |
| `span` | span | 原生 |  | — | 10 | 【原生】行内容器 |
| `bform` | form | 原生 |  | — | 2 | 【原生】`<form>` 标签 |
| `input` | input | 原生 |  | — | 6 | 【原生】`<input>` 输入框 |
| `bradio` | input | 原生 |  | — |  | 【原生】radio 输入 |
| `bcheck` | input | 原生 |  | — | 1 | 【原生】checkbox 输入 |
| `bbutton` | button | 原生 |  | — | 37 | 【原生】button 按钮 |
| `bimage` | img | 原生 |  | — | 3 | 【原生】`<img>` 图片 |
| `a` | a | 原生 |  | — | 6 | 【原生】链接 |
| `p` | p | 原生 |  | — |  | 【原生】段落 |
| `ul` | ul | 原生 |  | — | 3 | 【原生】无序列表 |
| `ol` | ol | 原生 |  | — |  | 【原生】有序列表 |
| `li` | li | 原生 |  | — | 7 | 【原生】列表项 |
| `header` | h3 | 原生 |  | — | 13 | 【原生】`<h3>` 标题 |
| `hr` | hr | 原生 |  | — | 13 | 【原生】分隔线 |
| `br` | br | 原生 |  | — | 2 | 【原生】换行 |

### supccan
| id | ExtJS 类型 | 库 | 容器 | 面板 | 用过的次数 | 干什么 |
|---|---|---|---|---|---|---|
| `treelist` | supcan | 原生 |  | — | 1 | 硕正报表：树形列表控件 |
| `report` | supcan | 原生 |  | — | 1 | 硕正报表：报表控件 |

## 四、层级结构：设计器不管，但有三种"约定"
> 下文的 `wb-debug.js` / `ide-debug.js` 是**项目自带的** WebBuilder 前端脚本；所注**行号取自本项目版本**，
> 换版本要按**符号名**（`append` / `setNewNode`）搜，别按行号找。

**先说硬事实**：设计器**不校验**父子关系 —— `Wb.append(parentNode, node)` 就是直接 `parentNode.appendChild(node)`（`wb-debug.js:2633`），拖到哪都行。

所以"能不能这么挂"由**运行时（ExtJS）**决定，改 xwl 时要靠下面三条约定判断：

1. **`container`**：只有 29 个是容器。非容器挂子控件运行时直接报错/被忽略。
2. **`autoNames`**：声明"我该挂在谁下面、挂上后叫什么"。例如 `toolbar` 的 `{"grid":"tbar","tree":"tbar"}` 表示挂在 grid 下时自动成为 `tbar`；`store` 的 `{"any":"store"}` 表示挂在任何容器下都叫 `store`。设计器逻辑见 `ide-debug.js:4397`（`setNewNode`）：`autoNames[父type] || autoNames.any`，且**父节点是 root（module/folder）时不用 `any`**。
3. **实测频次**：下面这张表是 2777 个真实 xwl 统计出来的**事实标准**。

### 4.1 实际父子结构（Top 45）
| 父 | → 子 | 次数 | 读法 |
|---|---|---|---|
| `array` | `column` | 20281 | **列数组 → 列**：最核心的结构，2 万处 |
| `toolbar` | `item` | 4797 | 工具栏 → 分隔符/占位/菜单项 |
| `toolbar` | `text` | 1745 | 工具栏 → 文本框（查询条件） |
| `grid` | `array` | 1743 | 表格 → 列数组（`itemId=columns`） |
| `panel` | `text` | 1568 | 面板 → 输入框 |
| `toolbar` | `combo` | 1411 | 工具栏 → 下拉框（查询条件） |
| `column` | `combo` | 1395 | 列 → 下拉编辑器 |
| `panel` | `combo` | 1317 | 面板 → 下拉框 |
| `grid` | `store` | 1315 | 表格 → 数据源（`url='m?xwl=…'`） |
| `column` | `number` | 1307 | 列 → 数字编辑器 |
| `column` | `text` | 1154 | 列 → 文本编辑器 |
| `module` | `dataprovider` | 1143 | 根 → SQL 执行器（SQL 文件的固定结构） |
| `module` | `window` | 1031 | 根 → 弹窗 |
| `window` | `text` | 996 | 弹窗 → 输入框 |
| `panel` | `grid` | 925 | 面板 → 表格 |
| `window` | `combo` | 788 | 弹窗 → 下拉框 |
| `combo` | `store` | 686 | **下拉框自带数据源** |
| `toolbar` | `date` | 679 | 工具栏 → 日期条件 |
| `toolbar` | `button` | 666 | 工具栏 → 按钮（查询/导出/导入） |
| `grid` | `toolbar` | 597 | 表格 → 工具栏（通常 itemId=`tbar`） |
| `module` | `query` | 595 | 根 → 查询控件（serverScript 型） |
| `item` | `item` | 587 | 工具栏项嵌套（菜单项） |
| `module` | `viewport` | 570 | 根 → 全屏容器（PC 页面标准结构） |
| `panel` | `panel` | 493 | 面板嵌套（布局分组） |
| `column` | `column` | 483 | **列分组（分组表头）** |
| `tab` | `panel` | 464 | 页签 → 页 |
| `viewport` | `panel` | 438 | 全屏 → 面板 |
| `array` | `toolbar` | 391 | 配置载体装工具栏 |
| `panel` | `number` | 381 | 面板 → 数字输入 |
| `window` | `panel` | 348 | 弹窗 → 面板 |
| `array` | `feature` | 326 | `features` 数组 → grid 特性 |
| `panel` | `date` | 282 | 面板 → 日期 |
| `window` | `number` | 237 | 弹窗 → 数字输入 |
| `panel` | `toolbar` | 209 | 面板 → 工具栏 |
| `panel` | `check` | 208 | 面板 → 复选框 |
| `panel` | `label` | 200 | 面板 → 标签 |
| `grid` | `tableview` | 190 | 表格 → 视图配置（`viewConfig`） |
| `window` | `grid` | 188 | 弹窗 → 表格（选择类弹窗） |
| `viewport` | `grid` | 180 | 全屏 → 表格 |
| `panel` | `textarea` | 165 | 面板 → 多行文本 |
| `form` | `file` | 152 | 表单里的上传字段（配合 `Wb.upload`） |
| `fieldset` | `text` | 134 | 分组框里的输入框 |
| `column` | `datetime` | 133 | 列 → 日期时间编辑器 |
| `module` | `toolbar` | 125 | 根 → 页面级工具栏 |
| `module` | `response` | 123 | 根 → 直接输出响应（`app.send` 型） |

### 4.2 典型骨架（照这个搭就不会错）
```text
module                          ← 每个 xwl 的根（页面钥匙：title/roles/inframe/pageLink）
├─ dataprovider                 ← 只有 serverScript 型数据源
│  （module.configs.serverScript + dataprovider.configs.sql）
└─ viewport / window / panel    ← 可见根容器
   ├─ toolbar  (itemId=tbar)    ← 查询条：text/combo/date/button/item
   └─ grid  (itemId=grid1)
      ├─ store                  ← 数据源（configs.url = 'm?xwl=…'）
      ├─ array (itemId=columns) ← 列数组
      │  └─ column × N          ← 列（列里可真嵌套 column = 分组表头；column 可挂 combo/number/text 作 editor）
      ├─ feature (itemId=features)
      └─ tableview (itemId=viewConfig)
```
其它常见组合：`tab → panel`（页签页）、`combo → store`（下拉数据源）、`form → 字段控件`、`window → form/panel`（弹窗）、`panel → panel`（嵌套布局）、`toolbar → item`（分隔符/菜单项）。

## 五、"配置载体"节点：最容易看不懂的一类
容器 `children` 里混着**两种东西**，一眼区分靠 `type`：

① **真子控件** —— 会渲染出来的（panel/grid/text/combo/button/toolbar…）；
② **配置载体** —— 不渲染，它的 **`itemId` 就是父控件的一个配置项名**，`children` 是那个配置项的值：

| 载体 type | 典型 itemId | 承载的配置项 | 次数 |
|---|---|---|---|
| `array` | `columns` / `features` / `dockedItems` / `items` / `series` / `axes` / `tools` / `buttons` | 数组型配置 | 1886 |
| `column` | 字段名（如 `CNTR_NO`） | 表格列定义 | 20765 |
| `item` | 工具栏项 id | toolbar 的子项 | 5434 |
| `feature` | `features` | grid 特性（可编辑/行号…） | 434 |
| `store` / `treestore` | `store` | 数据源 | 2065 |
| `tableview` | `viewConfig` | 视图配置 | 193 |
| `editing` | `plugins` | 编辑插件 | 0 |

`array` 的 itemId 实测取值分布：`columns`(1297)、`features`(322)、`dockedItems`(176)、`items`(45)、`series`(17)、`axes`(14)、`tools`(8)、`buttons`(7)

> **关键澄清**：`container` 标记只说明"能不能放**真子控件**"。`grid`/`module`/`combo` 这些没标容器的节点**照样有 `children`**——里面装的是上面这些**配置载体**（`grid.children = [store, array(columns), feature, tableview]`）。所以判断能不能加子节点，要分清是加"子控件"还是加"配置载体"。

## 六、选型建议（哪种情况用什么）
| 需求 | 用什么 | 备注 |
|---|---|---|
| PC 主页面骨架 | `viewport` → `panel`/`grid` | 根容器用一个即可 |
| 查询条件条 | `toolbar`（`itemId` 惯用 `tbar`）+ `text`/`combo`/`date` | 查询按钮 `load({out: app.tbar})` 自动收值 |
| 列表展示 | `grid` + `store` + `array(columns)` | 列用 `column`，`itemId`=字段名 |
| 弹窗编辑 | `window` → `form`/`panel` → 字段控件 | 保存按钮里用 `out: app.editWin` 收整表值 |
| 下拉选择 | `combo` + `store` | `store.url` 指向字典/代码类 SQL 文件 |
| 多页签 | `tab` → 多个 `panel` |  |
| 日期/时间条件 | `date` / `datetime` / `month` | 条件名 = `itemId` |
| 只要一个布尔条件 | `check` |  |
| 分组表头 | `column` 里再套 `column` |  |
| 单元格内编辑 | `column` 里挂 `combo`/`number`/`text` | 挂在 column 下即为该列的 editor |
| 纯展示字段 | `displayfield` | 只要显示不要输入框 |
| 多行备注 | `textarea` |  |
| 文件上传/导入 | `file` + `form` + `Wb.upload` | 见 SKILL.md 引用章节 |
| 传递隐藏参数 | `hidden` | `out:` 会把它一起送出 |
| 自由排版 / 富文本 | `div`/`span`/`p`（lib=3）或 `htmleditor` |  |
| 移动端页面 | `t` 前缀那一套（lib=2） | 与桌面控件一一对应，别混用 |
| SQL 数据源 | `module.configs.serverScript` + `dataprovider.configs.sql` | 文件名惯用 `transSql/queryXxx` |

## 七、改结构时的安全顺序
1. 先从这张表确认**目标控件的 id 与 ExtJS 类型**；
2. 用 `xwl.py schema <id> --controls <…/controls.json> --skeleton` 取**合法字段 + 设计器同款骨架**（键序 `configs, expanded, children, type, events`）；
3. 用 `xwl.py paths` / `xwl.py dump` 看清现有层级，再写 `patch` 的 `ops`（`path` 段可用 `@itemId` 寻址）；
4. `patch --dry-run` 看 diff → 真跑 → `xwl.py check`。
