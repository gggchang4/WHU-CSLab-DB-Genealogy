# WHU-CSLab-DB-Genealogy

武汉大学计算机学院数据库课程设计项目，主题为“寻根溯源”族谱管理系统。

当前仓库采用 `Python + Django + PostgreSQL + Bootstrap + ECharts` 技术路线，目标是在满足课程设计要求的前提下，逐步落地一个具备工程性、可维护性、可扩展性的族谱数据库系统。

## 项目目标

系统围绕“族谱建模、关系管理、查询分析、课程展示”展开，重点覆盖以下能力：

- 族谱基础信息管理
- 家族成员档案管理
- 亲子关系与婚姻关系维护
- 族谱协作邀请与协作者权限管理
- 祖先追溯、成员关系查询、亲缘路径查询
- 成员事件档案记录
- 课程要求中的统计 SQL、递归查询与性能分析展示

## 当前已实现

截至目前，仓库已经完成了以下内容：

- 数据库设计文档、ER 图、关系模式、约束设计
- PostgreSQL 初始 Schema 与约束/索引设计
- Django 项目骨架与自定义用户模型
- 用户注册、登录、退出
- 族谱创建与详情页
- 成员列表、创建、编辑、删除、详情页
- 成员事件档案的新增、编辑、删除
- 亲子关系与婚姻关系的新增、编辑、删除
- 协作邀请闭环与协作者管理
- 成员关系查询、亲缘路径查询
- 族谱统计分析页
- 树形预览页（ECharts）
- 族谱编辑、删除与祖先树展示
- 课程数据生成命令（支持 10 谱、5 万+ 单谱、10 万+ 总量目标）
- PostgreSQL `COPY` 成员导入命令与分支导出命令
- 四代后代查询的 `EXPLAIN ANALYZE` 基准命令

## 目录结构

```text
.
├─ backend/                 Django 后端项目
│  ├─ apps/
│  │  ├─ accounts/          用户与认证
│  │  ├─ core/              通用基类
│  │  └─ genealogy/         族谱核心业务
│  ├─ config/               Django 配置
│  ├─ templates/            页面模板
│  ├─ .env.example          环境变量示例
│  └─ manage.py             Django 入口
├─ docs/                    课程设计文档、数据库设计文档、ER 图
├─ scripts/
│  └─ dev/                  本地开发辅助脚本
├─ sql/                     PostgreSQL DDL
├─ requirements.txt         Python 依赖
└─ README.md
```

## 核心文档

- [课程需求说明](docs/project-spec.md)
- [数据库设计文档](docs/database-design.md)
- [ER 图 Mermaid 源文件](docs/er-diagram.mmd)
- [PostgreSQL 初始 Schema](sql/001_initial_schema.sql)

## 环境要求

建议本地环境如下：

- Python `3.12` 左右
- PostgreSQL `16` 或 `18`
- Windows PowerShell

当前 Python 依赖如下：

- `Django>=5.1,<5.2`
- `psycopg[binary]>=3.2,<3.3`
- `python-dotenv>=1.0,<2.0`

## 本地启动

### 最省心启动

如果你的 Python、PostgreSQL 已经安装完成，并且只想尽快把项目跑起来，推荐直接使用下面这组命令：

```powershell
.\scripts\dev\bootstrap.cmd
.\scripts\dev\runserver.cmd
```

第一次启动前，请先把 `backend/.env` 里的数据库密码改成你本机 PostgreSQL 的真实密码。按你当前本机配置，建议写成：

```env
POSTGRES_PASSWORD=Irving11
```

如果你只想做检查或运行测试，可以直接执行：

```powershell
.\scripts\dev\check.cmd
.\scripts\dev\test.cmd
```

### 推荐方式：使用统一脚本目录

当前项目已经把本地开发辅助脚本统一收口到 `scripts/dev/`，建议优先使用这组入口：

- `scripts/dev/bootstrap.ps1`
  - 初始化虚拟环境、安装依赖、复制 `backend/.env`、执行迁移
- `scripts/dev/manage.ps1`
  - Django 管理命令统一入口
- `scripts/dev/runserver.ps1`
  - 启动开发服务器
- `scripts/dev/check.ps1`
  - 执行 `manage.py check`
- `scripts/dev/test.ps1`
  - 执行当前后端测试集
- `scripts/dev/lint.ps1`
  - 执行 `ruff check backend`

同时也提供了对应的 `.cmd` 包装脚本，便于在 Windows 默认执行策略下直接运行：

- `scripts/dev/bootstrap.cmd`
- `scripts/dev/manage.cmd`
- `scripts/dev/runserver.cmd`
- `scripts/dev/check.cmd`
- `scripts/dev/test.cmd`
- `scripts/dev/lint.cmd`

如果你已经装好了 Python、PostgreSQL，并且只想快速启动，推荐直接执行：

```powershell
.\scripts\dev\bootstrap.cmd
.\scripts\dev\runserver.cmd
```

如果你只想跑检查或测试，可以执行：

```powershell
.\scripts\dev\check.cmd
.\scripts\dev\test.cmd
```

如需执行静态检查，可以执行：

```powershell
.\scripts\dev\lint.cmd
```

如需执行其他 Django 命令，也可以统一走：

```powershell
.\scripts\dev\manage.cmd createsuperuser
.\scripts\dev\manage.cmd shell
```

如果你更习惯直接执行 `.ps1`，但遇到 PowerShell 执行策略限制，可以改用：

```powershell
powershell -ExecutionPolicy Bypass -File .\scripts\dev\runserver.ps1
```

### 1. 创建虚拟环境并安装依赖

在仓库根目录执行：

```powershell
python -m venv .venv
.\.venv\Scripts\Activate.ps1
pip install -r requirements.txt
```

### 2. 配置环境变量

复制环境变量模板：

```powershell
Copy-Item backend\.env.example backend\.env
```

然后编辑 `backend/.env`，按你的本机 PostgreSQL 实际配置填写。模板内容如下：

```env
DJANGO_SECRET_KEY=replace-me
DJANGO_DEBUG=true
DJANGO_ALLOWED_HOSTS=127.0.0.1,localhost

POSTGRES_DB=genealogy
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

如果你本机当前 PostgreSQL 用户还是 `postgres`，数据库名准备使用 `genealogy`，那么你需要重点把 `POSTGRES_PASSWORD` 改成你自己的真实密码。

你前面提供的本机密码是 `Irving11`，所以你本地可以这样配：

```env
POSTGRES_DB=genealogy
POSTGRES_USER=postgres
POSTGRES_PASSWORD=Irving11
POSTGRES_HOST=127.0.0.1
POSTGRES_PORT=5432
```

### 3. 确保 PostgreSQL 已启动

如果 PostgreSQL 服务还没启动，可以在 PowerShell 中执行：

```powershell
Start-Service -Name postgresql-x64-18
```

如果你的服务名不是这个，可以先查看：

```powershell
Get-Service | Where-Object { $_.Name -like "postgres*" }
```

### 4. 创建数据库

如果 `genealogy` 数据库还没创建，先在 PostgreSQL 中创建它。你可以使用 `psql` 或 pgAdmin。

`psql` 示例：

```powershell
psql -U postgres -h 127.0.0.1 -p 5432
```

进入后执行：

```sql
CREATE DATABASE genealogy;
```

### 5. 执行迁移

```powershell
.\.venv\Scripts\python.exe backend\manage.py migrate
```

或者使用统一脚本入口：

```powershell
.\scripts\dev\manage.cmd migrate
```

如需创建后台管理员账号：

```powershell
.\.venv\Scripts\python.exe backend\manage.py createsuperuser
```

或者：

```powershell
.\scripts\dev\manage.cmd createsuperuser
```

### 6. 启动开发服务器

```powershell
.\.venv\Scripts\python.exe backend\manage.py runserver
```

或者：

```powershell
.\scripts\dev\runserver.cmd
```

启动后可访问：

- 首页与业务入口：<http://127.0.0.1:8000/>
- 登录页：<http://127.0.0.1:8000/accounts/login/>
- 注册页：<http://127.0.0.1:8000/accounts/register/>
- Django Admin：<http://127.0.0.1:8000/admin/>
- 健康检查：<http://127.0.0.1:8000/health/>

## 测试与自检

### Django 配置检查

```powershell
.\.venv\Scripts\python.exe backend\manage.py check
```

或者：

```powershell
.\scripts\dev\check.cmd
```

### 运行测试

```powershell
.\.venv\Scripts\python.exe backend\manage.py test apps.accounts apps.genealogy
```

或者：

```powershell
.\scripts\dev\test.cmd
```

### 编译检查

```powershell
.\.venv\Scripts\python.exe -m compileall backend
```

### 静态检查

仓库已经补充了 `ruff` 配置文件 [`pyproject.toml`](pyproject.toml)，并提供了统一脚本入口：

```powershell
.\scripts\dev\lint.cmd
```

如果本地尚未安装 `ruff`，可以手动安装：

```powershell
.\.venv\Scripts\python.exe -m pip install ruff
```

## 课程命令

除了 Web 页面外，当前仓库还补充了面向课程验收的数据库工程命令，统一通过 `manage.py` 执行。

### 1. 生成课程规模测试数据

默认目标对齐课程要求：`10` 个族谱、总计 `100000` 成员、其中至少 `1` 个族谱达到 `50000` 成员，并保留 `30` 代链路深度。

```powershell
.\.venv\Scripts\python.exe backend\manage.py generate_course_dataset
```

如果你只想先做一个小规模 smoke test，也可以这样：

```powershell
.\.venv\Scripts\python.exe backend\manage.py generate_course_dataset --genealogy-count 2 --total-members 80 --large-members 40 --generations 10
```

### 2. 用 PostgreSQL COPY 批量导入成员 CSV

CSV 表头支持以下字段：

`full_name,surname,given_name,gender,birth_year,death_year,is_living,generation_label,seniority_text,branch_name,biography`

执行方式：

```powershell
.\.venv\Scripts\python.exe backend\manage.py import_members_copy --genealogy-id 2 --csv output\coursework\sample-import\members.csv
```

### 3. 导出某个分支的备份 CSV

这个命令会从指定根成员向下递归导出当前分支，并写出：

- `branch_members.csv`
- `branch_parent_child_relations.csv`
- `branch_marriages.csv`

执行方式：

```powershell
.\.venv\Scripts\python.exe backend\manage.py export_branch_copy --genealogy-id 1 --root-member-id 1 --output-dir output\coursework\branch-export
```

### 4. 生成有索引 / 无索引的 EXPLAIN 基准报告

当前已补齐“四代后代查询”的索引对比命令。命令会在事务内临时移除相关索引、执行 `EXPLAIN ANALYZE`，最后自动回滚，不会真的破坏索引。

```powershell
.\.venv\Scripts\python.exe backend\manage.py benchmark_parent_lookup --genealogy-id 1 --root-member-id 1 --output output\coursework\benchmarks\parent_lookup.md
```

## 当前开发约束

为了保证课程设计阶段的工程性和后续可维护性，当前代码遵循以下原则：

- 数据库事实模型以 `docs/database-design.md` 和 `sql/001_initial_schema.sql` 为准
- 亲缘关系只显式存储基础边：`parent_child_relations` 与 `marriages`
- 兄弟、祖孙、叔侄、姻亲、亲缘路径等关系统一通过查询推导
- “第几代”不作为事实字段存储，后续通过递归 CTE 推导
- 成员档案采用“主档 + 事件表”结构，避免过早过度拆表
- Django 模型服务于业务开发，但复杂一致性仍优先由 PostgreSQL 约束、索引、触发器兜底

## 下一步开发方向

后续建议继续推进以下内容：

- 成员树形展示继续增强
- 统计 SQL 与课程展示页完善
- 更完整的前端交互与页面美化
- 课程报告截图、实验报告与最终演示材料整理

## 说明

- 本项目用于武汉大学数据库课程设计学习与实现
- 当前处于持续迭代阶段，README 会随着开发同步更新
- 若后续引入前端框架，会在保留现有领域模型稳定性的前提下逐步重构界面层
