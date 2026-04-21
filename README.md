# Lana Project

Phase 0 scaffold for the crypto data warehouse project.

## 1) Backend setup

```bash
cd backend
python3 -m venv .venv
source .venv/bin/activate
pip install -r requirements.txt
cp ../.env.example .env
```

Run API:

```bash
uvicorn app.main:app --reload --host 0.0.0.0 --port 8000
```

Run migration baseline:

```bash
alembic upgrade head
```

## 2) Frontend setup

```bash
cd frontend
npm install
npm run dev
```

Open http://localhost:3000

## 3) Health checks

- API: `GET /api/health`
- DB: `GET /api/health/db`

## 4) 首次上线：分批自动初始化

首次上线建议先跑一次分批初始化脚本（会打印每个币种的 K 线/OI 入库数量）：

```bash
cd backend
source .venv/bin/activate
python -m app.tasks.bootstrap_auto_init --refresh-auto-pool --batch-size 3 --sleep-seconds 2
```

常用参数：
- `--days`：回补天数（默认 30）
- `--batch-size`：每批初始化币种数（默认 5）
- `--sleep-seconds`：每批休眠秒数（默认 2）
- `--max-rounds`：最多跑多少批（默认 0，直到跑完）

## 5) 日常自动任务（无需手动初始化）

后端启动后调度器会自动循环执行：
1. 刷新自动池
2. 自动初始化新入池且无历史数据的币
3. 执行 15 分钟增量采集（K线 + OI）
4. 每日巡检最近 24h 缺口（K线 + OI）

关键环境变量（`backend/.env`）：
- `SCHEDULER_ENABLED=true`
- `SCHEDULER_INTERVAL_MINUTES=15`
- `SCHEDULER_STEP_RETRY_COUNT=2`
- `SCHEDULER_STEP_RETRY_DELAY_SECONDS=1.5`
- `GAP_CHECK_ENABLED=true`
- `GAP_CHECK_HOURS=24`
- `GAP_CHECK_MAX_SYMBOLS=300`
- `GAP_CHECK_HOUR=0`
- `GAP_CHECK_MINUTE=20`
- `AUTO_INIT_NEW_SYMBOLS=true`
- `AUTO_INIT_DAYS=30`
- `AUTO_INIT_MAX_SYMBOLS_PER_CYCLE=5`

## 6) 缺口巡检与补数接口

触发最近 24h 缺口巡检（会写入任务日志，`task_type=gap_inspect`）：

```bash
curl -X POST "http://127.0.0.1:8080/api/collect/gap-inspect?hours=24&max_symbols=300"
```

触发缺口补数（默认只补缺口币，`task_type=gap_backfill`）：

```bash
curl -X POST "http://127.0.0.1:8080/api/collect/gap-backfill" \
  -H "Content-Type: application/json" \
  -d '{"hours":24,"max_symbols":300,"only_missing":true}'
```
