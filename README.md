# webbuilder-xwl-patch · 技能开发仓库

本仓库是 **webbuilder-xwl-patch** 技能的**开发仓库**：仓库根放开发资产，
**技能本体在 [`webbuilder-xwl-patch/`](webbuilder-xwl-patch/)**（安装时只装这一层）。

## 仓库导航

| 位置 | 是什么 |
|---|---|
| [`webbuilder-xwl-patch/`](webbuilder-xwl-patch/) | **技能本体（也是安装目录）**：入口 [`SKILL.md`](webbuilder-xwl-patch/SKILL.md)、使用者文档 [`README.md`](webbuilder-xwl-patch/README.md)、`references/`、`examples/`、`scripts/xwl.py` |
| [`scripts/selftest.py`](scripts/selftest.py) | **开发自测入口**（只在源码树里跑；安装副本不含它） |
| [`tests/baseline.json`](tests/baseline.json) | 自检基线（块名等） |
| [`.github/workflows/selftest.yml`](.github/workflows/selftest.yml) | CI：自测 ＋ 安装布局校验 |

## 最小用法

```bash
# 开发自测（在仓库根执行；源码树没有 .git 时加 --allow-nogit）
python scripts/selftest.py

# 技能的命令行入口
python webbuilder-xwl-patch/scripts/xwl.py --help
```

装到本机、升级与「命令在哪个目录跑」见
[`webbuilder-xwl-patch/references/distribution.md`](webbuilder-xwl-patch/references/distribution.md)。

## 边界

- 本仓库**只放技能开发资产**。技能怎么用、有哪些命令与规则，正本是
  [`webbuilder-xwl-patch/SKILL.md`](webbuilder-xwl-patch/SKILL.md) 与其 `references/` ——
  本文件只作仓库导航，不复制技能正文、不另立第二份说明。
- 仓库根**不放 `SKILL.md`**：安装器会把仓库内容当技能目录，根上出现 `SKILL.md` 会改变安装语义。
- 发布材料、计划、事项台账与验收记录在**工作区**维护，**不随本仓库分发**；本文件不提供指向仓库外的链接。
