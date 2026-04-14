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
- 数据库设计文档
- ER 图与关系模型
- PostgreSQL 初始化 Schema

后续计划补充：

- 数据生成脚本
- 查询示例与性能测试结果
- 应用界面原型

## Database Design Assets

当前已经落地的数据库设计资产：

- [数据库设计文档](docs/database-design.md)
- [ER 图 Mermaid 源文件](docs/er-diagram.mmd)
- [PostgreSQL 初始化 DDL](sql/001_initial_schema.sql)

## Backend Scaffold

当前已补充 Django 后端骨架，便于继续落地模型与业务开发：

- [依赖清单](requirements.txt)
- [环境变量模板](backend/.env.example)
- [Django 入口](backend/manage.py)
- [项目配置](backend/config/settings.py)
- [账户模型](backend/apps/accounts/models.py)
- [账户管理器](backend/apps/accounts/managers.py)
- [族谱领域模型](backend/apps/genealogy/models.py)
- [初始迁移](backend/apps/accounts/migrations/0001_initial.py)
- [PostgreSQL 特性迁移](backend/apps/genealogy/migrations/0002_postgres_features.py)

当前后端脚手架的定位是：

- 先把数据库设计映射到 Django 模型层，方便后续继续补迁移、服务层、接口层和管理后台
- 当前重点覆盖“领域建模”和“约束表达”，尚未完成注册登录、权限中间件、Django Admin、REST API 和前端页面
- 当前数据库设计的权威来源仍然是 [数据库设计文档](docs/database-design.md) 和 [PostgreSQL 初始化 DDL](sql/001_initial_schema.sql)
- Django 模型层已经尽量对齐物理模型，但复杂约束仍以 PostgreSQL 层的约束、索引和触发器为准
- 当前已切换到 Django 自定义用户模型路线，后续注册、登录、会话和后台权限都应基于 `AUTH_USER_MODEL`

## Current Architecture

当前仓库的实现结构如下：

- `docs/`
  - 课程需求整理、数据库设计文档、ER 图源文件
- `sql/`
  - PostgreSQL 初始化 Schema
- `backend/`
  - Django 项目骨架与领域模型
- `requirements.txt`
  - 当前后端依赖

当前后端分层目标：

- `apps.accounts`
  - 系统用户领域模型
- `apps.genealogy`
  - 族谱、邀请、协作者、成员、事件、亲子关系、婚姻关系
- `apps.core`
  - 通用时间戳基类

## Current Status

截至目前，已经完成：

- 课程需求梳理
- ER 图与关系模式设计
- PostgreSQL 初始化 DDL
- Django 后端项目骨架
- Django 领域模型初版
- Django 初始迁移文件
- PostgreSQL 专属迁移补丁
- Django 自定义用户模型与 Admin 基础接入

尚未完成但下一步会继续补充：

- 注册/登录与权限系统
- 数据生成脚本
- 课程要求对应的 SQL 查询
- `EXPLAIN` 与性能测试材料
- 页面原型与演示流程

## Quick Start

如果你要在本地继续推进 Django 后端，可以按下面的顺序操作：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
Copy-Item backend\.env.example backend\.env
```

当前项目使用 PostgreSQL，默认环境变量见 [backend/.env.example](backend/.env.example)。

安装依赖之后，后续常用命令会是：

```powershell
cd backend
python manage.py check
python manage.py migrate
python manage.py runserver
```

说明：

- 当前仓库已经提交初始 migration，并额外补了一层 PostgreSQL 专属 migration，用来纳入 `pg_trgm`、复合外键和触发器
- 当前模型层主要服务于建模与开发起步，复杂约束仍建议以 PostgreSQL DDL 与 PostgreSQL migration 为最终校准依据
- 如果后续修改模型后执行 `makemigrations`，建议先检查是否会和 [sql/001_initial_schema.sql](sql/001_initial_schema.sql) 的数据库事实来源发生偏移
- 当前项目已经切到 Django 自定义用户模型路线，后续注册、登录、会话与后台权限都应基于 `AUTH_USER_MODEL`
- 如果要得到完整可运行的认证环境，推荐使用 Django migration 建库，而不是只手动执行业务 SQL 文件

## Development Notes

从当前版本继续开发时，建议遵循下面的原则：

- 先以 [sql/001_initial_schema.sql](sql/001_initial_schema.sql) 和 [docs/database-design.md](docs/database-design.md) 作为数据库事实来源
- Django 模型新增字段或约束前，先确认不会破坏课程设计里的 3NF/BCNF 口径
- 亲缘链路、祖先递归、代际统计等复杂查询优先按 PostgreSQL SQL 设计，再决定是否封装进 ORM
- 当前 `users` 已作为 Django 自定义用户模型接入认证体系，但业务权限边界仍应由族谱协作模型控制，而不是只依赖 Django 的 `staff/superuser` 标志

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
