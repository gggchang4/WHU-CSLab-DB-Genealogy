# WHU-CSLab-DB-Genealogy

武汉大学计算机学院数据库课程设计项目，主题为 `"寻根溯源" 族谱管理系统`。

本仓库当前处于逐步开发阶段，目标是围绕课程要求完成一个可演示、可建模、可生成大规模数据、可进行复杂关系查询与性能分析的族谱管理系统。`README` 会随着项目推进持续更新。

## Project Overview

本项目聚焦多用户协作的族谱管理场景。系统需要支持多个族谱，每个族谱对应一个家族，并记录：

- 族谱基本信息，如谱名、姓氏、修谱时间、创建用户
- 家族成员基本信息，如姓名、性别、生卒年、生平简介
- 成员之间的亲子关系与婚姻关系
- 多用户协作维护与邀请机制

课程要求中的关键难点包括：

- 家族层级深度不确定
- 存在同名同姓但不同辈分的成员
- 需要高效追溯祖先与查找直系后代
- 需要判断两名成员之间是否存在亲缘关系，并展示链路

## Course Requirements Summary

项目最终需要覆盖以下几类内容：

- 基础图形化界面
  - 用户注册、登录
  - 族谱与成员的增删改查
  - 族谱邀请协作者
  - Dashboard 展示家族总人数和男女比例
  - 树形预览、祖先查询、亲缘关系链路查询
- 数据库设计
  - ER 图
  - 关系模式转换
  - 3NF 或 BCNF 分析
  - 主键、外键与约束设计
- 数据工程
  - 生成至少 10 个族谱
  - 整体不少于 100,000 条成员数据
  - 至少一个族谱拥有 50,000+ 成员
  - 至少模拟 30 代传承关系
  - 使用 PostgreSQL `COPY` 进行批量导入导出
- SQL 与性能优化
  - 基础查询与递归 CTE
  - 统计分析 SQL
  - 索引设计
  - `EXPLAIN` 执行计划与性能对比

更完整的开发参考见 [docs/project-spec.md](/g:/WHU-CSLab-DB-Genealogy/docs/project-spec.md)。

## Planned Scope

当前计划优先推进以下几个方向：

1. 数据库建模与表结构设计
2. 模拟数据生成脚本
3. 核心 SQL 查询实现
4. 基础 Web 界面原型
5. 报告与验收材料整理

## Suggested Tech Direction

课程 PDF 允许多种技术路线。为了便于后续开发与演示，本仓库当前默认采用如下方向作为后续实现参考：

- Database: PostgreSQL
- Backend: Python Web framework
- Frontend: simple web UI for demo
- Data generation: Python scripts
- Query validation: SQL files plus `EXPLAIN` analysis

这部分是当前的默认方向，不代表最终方案不可调整。

## Repository Status

当前仓库刚完成项目资料整理，代码实现尚在逐步补充中。

已完成：

- 课程 PDF 收集
- 项目需求梳理文档
- 开源仓库 README 初版

后续计划补充：

- 数据库设计文档
- ER 图和关系模型
- 初始化 SQL
- 数据生成脚本
- 查询示例与性能测试结果
- 应用界面原型

## Acceptance Deliverables

根据课程要求，最终提交材料至少应包括：

- 实验报告
- ER 图
- 关系模型与 3NF 分析
- 索引与约束说明
- 数据生成方法说明
- 所用 RDBMS 名称与版本
- 对应 SQL 语句及执行结果截图
- 数据生成工具源码
- 数据库导出或备份文件

同时需要现场演示系统功能，并回答相关问题。

## References

- FamilySearch: <https://www.familysearch.org/zhHant/chinese/>
- 华谱网: <https://www.zhonghuapu.com/>
- 大谱师: <https://myfamilybook.cn/>
- 族谱网: <https://www.zupu.cn/zp/>

## Notes

- 本项目用于武汉大学计算机学院数据库课程设计学习与实践。
- 仓库内容会随着开发推进持续更新。
- 如果后续补充了代码、数据脚本、报告模板或演示截图，README 会同步扩展。
