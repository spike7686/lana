"use client";

import Link from "next/link";
import { useEffect, useState } from "react";

import { fetchTasks, refreshAutoPool, runIncremental, type TaskLogItem } from "@/lib/api";

export default function TasksPage() {
  const [items, setItems] = useState<TaskLogItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [taskTypeFilter, setTaskTypeFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");

  async function load() {
    setLoading(true);
    try {
      const rows = await fetchTasks({
        limit: 100,
        task_type: taskTypeFilter === "all" ? undefined : taskTypeFilter,
        status:
          statusFilter === "all"
            ? undefined
            : (statusFilter as "running" | "success" | "failed"),
      });
      setItems(rows);
    } catch (err) {
      setMessage(`加载任务失败: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void load();
  }, [taskTypeFilter, statusFilter]);

  async function onRunRefreshAuto() {
    setBusy(true);
    setMessage("触发自动池刷新中...");
    try {
      const result = await refreshAutoPool();
      setMessage(`自动池刷新完成: ${JSON.stringify(result)}`);
      await load();
    } catch (err) {
      setMessage(`自动池刷新失败: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onRunIncremental() {
    setBusy(true);
    setMessage("触发增量采集中...");
    try {
      const result = await runIncremental();
      setMessage(`增量采集已触发: ${JSON.stringify(result)}`);
      await load();
    } catch (err) {
      setMessage(`增量采集失败: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>任务监控</h1>
      <div className="row gap">
        <Link href="/pool" className="btn ghost">返回池子</Link>
        <button className="btn" disabled={busy} onClick={onRunRefreshAuto}>触发 refresh-auto</button>
        <button className="btn" disabled={busy} onClick={onRunIncremental}>触发 incremental-run</button>
        <button className="btn ghost" disabled={busy || loading} onClick={() => void load()}>刷新列表</button>
      </div>

      <section className="panel">
        <h2>筛选</h2>
        <div className="row gap">
          <select className="select" value={taskTypeFilter} onChange={(e) => setTaskTypeFilter(e.target.value)}>
            <option value="all">task_type: 全部</option>
            <option value="init_symbol">init_symbol</option>
            <option value="incremental_run">incremental_run</option>
            <option value="gap_inspect">gap_inspect</option>
            <option value="gap_backfill">gap_backfill</option>
          </select>
          <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">status: 全部</option>
            <option value="running">running</option>
            <option value="success">success</option>
            <option value="failed">failed</option>
          </select>
          <span className="msg">共 {items.length} 条</span>
        </div>
      </section>

      <section className="panel">
        <h2>任务列表</h2>
        {loading ? (
          <p>加载中...</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>ID</th>
                <th>Type</th>
                <th>Status</th>
                <th>Duration(s)</th>
                <th>Started</th>
                <th>Scope</th>
                <th>Summary</th>
                <th>Error</th>
              </tr>
            </thead>
            <tbody>
              {items.map((row) => (
                <tr key={row.id}>
                  <td>{row.id}</td>
                  <td>{row.task_type}</td>
                  <td>
                    <StatusPill status={row.status} />
                  </td>
                  <td>{row.duration_seconds == null ? "-" : row.duration_seconds.toFixed(2)}</td>
                  <td>{formatUtc(row.started_at)}</td>
                  <td><JsonDetails value={row.scope} /></td>
                  <td><JsonDetails value={row.summary} /></td>
                  <td className="error-cell">{row.error_message ?? "-"}</td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>

      {message ? <p className="msg">{message}</p> : null}
    </main>
  );
}

function StatusPill({ status }: { status: "running" | "success" | "failed" }) {
  const cls =
    status === "success"
      ? "pill success"
      : status === "failed"
        ? "pill failed"
        : "pill running";
  return <span className={cls}>{status}</span>;
}

function formatUtc(value: string): string {
  return new Date(value).toISOString().replace("T", " ").replace("Z", " UTC");
}

function JsonDetails({ value }: { value: Record<string, unknown> }) {
  const text = JSON.stringify(value, null, 2);
  return (
    <details className="json-details">
      <summary>查看</summary>
      <pre>{text}</pre>
    </details>
  );
}
