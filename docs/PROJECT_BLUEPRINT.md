# 加密数据仓库项目蓝图

## 1. 项目目标
构建一个用于合约标的分析的数据平台，具备以下能力：
- 基于 `15m` 与 `1h` 涨幅榜自动生成标的池，并做交叉去重
- 过滤稳定币与主流币
- 支持手动增删标的，且可控制采集生命周期
- 初始化回补最近 30 天的 `15m` 与 `1h` K 线和 OI
- 每 15 分钟执行一次增量更新
- 前端展示标的池、蜡烛图、OI 曲线、项目简介，并支持单币种导出

## 2. 范围（V1）
### 包含内容
- 基于 Binance 的数据采集
- 标的池管理（自动 + 手动）
- K 线（`15m`、`1h`）与 OI（`15m`、`1h`）采集
- 项目简介元数据采集与存储
- 按币种与周期导出数据
- Web 看板浏览与图表展示

### 不包含内容（V1）
- 多交易所聚合
- 策略回测引擎
- 实时 WebSocket 流式管道
- 多租户鉴权与权限系统

## 3. 系统架构
- 后端 API：FastAPI
- 调度器：APScheduler（15 分钟周期任务）
- 数据库：PostgreSQL（可选 TimescaleDB 扩展）
- 前端：Next.js + lightweight-charts
- 部署：本机进程方式运行（无 Docker）

## 4. 核心业务规则
1. 自动标的池生成
- 拉取 `15m` 与 `1h` 涨幅榜
- 合并方式可配置（并集/交集，默认并集）
- 对合约标的去重
- 根据配置列表过滤稳定币与主流币

2. 手动控制
- 手动添加：标的立即进入 `active`
- 手动删除：标的标记为 `inactive`，增量任务必须跳过
- 手动初始化按钮：触发该标的近 30 天历史回补

3. 初始化策略
- 回补近 30 天 `15m`/`1h` K 线和 OI
- 仅使用 Upsert 写入（幂等）

4. 增量更新策略
- 每 15 分钟运行一次
- 仅处理 `active` 状态标的
- 从各标的最后一条时间戳继续向后补齐
- 记录重试与任务日志

## 5. 建议仓库结构
```text
lanaproject/
  backend/
    app/
      api/
      core/
      db/
      models/
      schemas/
      services/
        binance/
        collector/
        pool/
      scheduler/
      tasks/
      main.py
    alembic/
    tests/
    requirements.txt
  frontend/
    src/
      app/
      components/
      lib/
      services/
    package.json
  docs/
    PROJECT_BLUEPRINT.md
  .env.example
```

## 6. 数据模型蓝图

## 6.1 `asset_pool`
用途：标的池主表，管理自动/手动来源与启用状态。
- `id` BIGSERIAL PK
- `symbol` VARCHAR(32) UNIQUE NOT NULL
- `status` VARCHAR(16) NOT NULL CHECK in (`active`,`inactive`)
- `source` VARCHAR(16) NOT NULL CHECK in (`auto`,`manual`)
- `list_tags` JSONB DEFAULT '{}'::jsonb
- `created_at` TIMESTAMPTZ NOT NULL DEFAULT now()
- `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now()

索引：
- unique(`symbol`)
- index(`status`)

## 6.2 `kline_15m`
- `symbol` VARCHAR(32) NOT NULL
- `open_time` TIMESTAMPTZ NOT NULL
- `open` NUMERIC(28,12) NOT NULL
- `high` NUMERIC(28,12) NOT NULL
- `low` NUMERIC(28,12) NOT NULL
- `close` NUMERIC(28,12) NOT NULL
- `volume` NUMERIC(28,12) NOT NULL
- `quote_volume` NUMERIC(28,12)
- `trades` INTEGER
- PK(`symbol`,`open_time`)

## 6.3 `kline_1h`
结构同 `kline_15m`，PK(`symbol`,`open_time`)。

## 6.4 `oi_15m`
- `symbol` VARCHAR(32) NOT NULL
- `ts` TIMESTAMPTZ NOT NULL
- `sum_open_interest` NUMERIC(28,12)
- `sum_open_interest_value` NUMERIC(28,12)
- PK(`symbol`,`ts`)

## 6.5 `oi_1h`
结构同 `oi_15m`，PK(`symbol`,`ts`)。

## 6.6 `asset_profile`
- `symbol` VARCHAR(32) PRIMARY KEY
- `name` VARCHAR(128)
- `sector` VARCHAR(128)
- `description` TEXT
- `website` TEXT
- `twitter` TEXT
- `extra` JSONB DEFAULT '{}'::jsonb
- `updated_at` TIMESTAMPTZ NOT NULL DEFAULT now()

## 6.7 `collector_task_log`
- `id` BIGSERIAL PK
- `task_type` VARCHAR(64) NOT NULL
- `scope` JSONB DEFAULT '{}'::jsonb
- `started_at` TIMESTAMPTZ NOT NULL
- `finished_at` TIMESTAMPTZ
- `status` VARCHAR(16) NOT NULL CHECK in (`running`,`success`,`failed`)
- `summary` JSONB DEFAULT '{}'::jsonb
- `error_message` TEXT

## 7. API 蓝图（V1）

## 7.1 标的池管理
- `GET /api/pool`
  - Query：`status`、`source`
  - 返回标的池列表

- `POST /api/pool/refresh-auto`
  - 根据涨幅榜逻辑刷新自动池
  - 返回 inserted/updated/skipped 数量

- `POST /api/pool/manual-add`
  - Body：`{ "symbol": "1000PEPEUSDT", "init_now": true }`
  - 手动添加标的，并可选立即初始化

- `POST /api/pool/manual-remove`
  - Body：`{ "symbol": "1000PEPEUSDT" }`
  - 标记为 `inactive`

## 7.2 采集任务
- `POST /api/collect/init-symbol`
  - Body：`{ "symbol": "1000PEPEUSDT", "days": 30 }`
  - 回补该标的 `15m`/`1h` K 线与 OI

- `POST /api/collect/init-pool`
  - Body：`{ "days": 30 }`
  - 回补所有 active 标的

- `POST /api/collect/incremental-run`
  - 立即触发一次增量采集

- `GET /api/collect/tasks`
  - 查询近期任务日志

## 7.3 市场数据查询
- `GET /api/market/{symbol}/kline?interval=15m&start=...&end=...`
- `GET /api/market/{symbol}/oi?interval=15m&start=...&end=...`
- `GET /api/market/{symbol}/profile`

## 7.4 导出
- `GET /api/export/{symbol}?interval=15m&type=kline&format=csv`
- `GET /api/export/{symbol}?interval=1h&type=oi&format=csv`

## 8. 调度设计

任务：
1. `pool_auto_refresh_job`
- 每 15 分钟执行：`0/15/30/45`
- 刷新涨幅榜并更新 `asset_pool`

2. `incremental_collect_job`
- 每 15 分钟执行：`1/16/31/46`
- 为所有 active 标的补齐新 K 线/OI

3. `profile_refresh_job`
- 每日执行（例如服务器本地时间 03:00）
- 刷新 active 标的项目信息

运行规则：
- 单任务加锁，避免并发重入
- 失败重试策略：最多 3 次，指数退避
- 失败写入 `collector_task_log`

## 9. Binance 采集规则

K 线：
- 接口：futures kline 对应周期接口
- 周期：`15m`、`1h`
- 回补需按窗口分页，满足接口 `limit` 限制

OI：
- 接口：`openInterestHist`
- 周期：`15m`、`1h`
- 历史可用范围：仅滚动最近 30 天
- 要保留长期历史，必须持续落库归档

## 10. 过滤策略
在 `backend/app/core/settings` 维护两份可配置名单：
- `stablecoins_blacklist`：
  - `USDT`, `USDC`, `FDUSD`, `BUSD`, `TUSD`, `DAI`, `USDP`
- `majors_blacklist`：
  - `BTC`, `ETH`, `BNB`, `SOL`, `XRP`, `ADA`, `DOGE`, `TRX`

规则：
- base asset 命中任一名单，自动池剔除
- 手动添加可选覆盖过滤（参数 `force=true`）

## 11. 前端蓝图

页面：
1. `/pool`
- active 标的表格
- source/status 标签
- 最近更新时间
- 手动添加/删除操作
- 单标的初始化按钮

2. `/symbol/[symbol]`
- `15m/1h` 切换
- 蜡烛图（OHLCV）
- OI 曲线（折线）
- 项目信息面板
- 数据下载按钮

组件：
- `SymbolTable`
- `CandlestickPanel`
- `OILinePanel`
- `ProfileCard`
- `ExportActions`

## 12. 分阶段交付计划

Phase 0：项目初始化（1-2 天）
- 搭建后端/前端脚手架
- 数据库迁移基线
- 健康检查与环境配置

验收标准：
- 本机可分别启动前后端服务
- PostgreSQL 数据库迁移执行通过

Phase 1：采集 MVP（2-4 天）
- 实现 Binance K 线/OI 客户端
- 实现 `init-symbol` 接口
- 实现 15 分钟增量调度
- 实现幂等入库

验收标准：
- 单币可完成近 30 天初始化
- 增量任务能正确追加新数据

Phase 2：标的池自动化 + 手动控制（2-3 天）
- 实现 `15m + 1h` 涨幅榜选币逻辑
- 实现过滤 + 去重 + 入库
- 实现手动添加/删除/初始化

验收标准：
- 自动池刷新稳定
- 被删除标的不再参与增量更新

Phase 3：看板与导出（3-5 天）
- 标的池列表页
- 单标的详情页（图表 + 简介）
- CSV 导出接口与前端按钮

验收标准：
- 用户可查看并导出单币种数据

Phase 4：稳定性加固（2-3 天）
- 重试/退避/任务锁
- 数据缺口检测与修复接口
- 监控与结构化日志

验收标准：
- 连续运行 7 天，无严重数据断档

## 13. 质量门禁
- 标的过滤/去重逻辑单元测试
- 采集幂等入库集成测试
- 导出 API 格式契约测试
- 调度任务冒烟测试

## 14. 风险清单
1. 接口限频或节流
- 缓解：限速 + 分批 + 退避重试

2. OI 仅保留滚动 30 天
- 缓解：严格 15 分钟落库 + 缺口检测

3. 时间边界错位
- 缓解：统一 UTC，按 K 线开盘时间对齐

4. 项目信息源不稳定
- 缓解：本地覆盖表 + 缓存过期策略

## 15. 立即开工顺序
1. 建立 FastAPI + SQLAlchemy + Alembic 脚手架
2. 按第 6 节落地数据库结构
3. 实现 Binance K 线/OI 分页采集封装
4. 优先交付 `init-symbol` 与 `incremental-run`
5. 接入调度器与任务日志
6. 数据链路稳定后开始前端池子页面
