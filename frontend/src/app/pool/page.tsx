"use client";

import Link from "next/link";
import { useEffect, useMemo, useState } from "react";

import {
  fetchPool,
  manualAddSymbol,
  manualRemoveSymbol,
  type PoolItem,
  refreshAutoPool,
} from "@/lib/api";
import { formatUtc8 } from "@/lib/time";

export default function PoolPage() {
  const [items, setItems] = useState<PoolItem[]>([]);
  const [loading, setLoading] = useState(true);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [symbolInput, setSymbolInput] = useState("");
  const [sectorFilter, setSectorFilter] = useState("all");
  const [tierFilter, setTierFilter] = useState("all");
  const [statusFilter, setStatusFilter] = useState("all");
  const [sourceFilter, setSourceFilter] = useState("all");

  const activeCount = useMemo(() => items.filter((x) => x.status === "active").length, [items]);
  const sectorOptions = useMemo(() => {
    const values = new Set<string>();
    for (const row of items) {
      if (row.sector && row.sector.trim()) {
        values.add(row.sector.trim());
      }
    }
    return Array.from(values).sort((a, b) => a.localeCompare(b));
  }, [items]);

  const filteredItems = useMemo(() => {
    return items.filter((row) => {
      if (sectorFilter !== "all" && (row.sector ?? "-") !== sectorFilter) {
        return false;
      }
      if (tierFilter !== "all" && (row.tier ?? "-") !== tierFilter) {
        return false;
      }
      if (statusFilter !== "all" && row.status !== statusFilter) {
        return false;
      }
      if (sourceFilter !== "all" && row.source !== sourceFilter) {
        return false;
      }
      return true;
    });
  }, [items, sectorFilter, tierFilter, statusFilter, sourceFilter]);

  async function loadPool() {
    setLoading(true);
    try {
      const rows = await fetchPool();
      setItems(rows);
    } catch (err) {
      setMessage(`加载失败: ${(err as Error).message}`);
    } finally {
      setLoading(false);
    }
  }

  useEffect(() => {
    void loadPool();
  }, []);

  async function onRefreshAuto() {
    setBusy(true);
    setMessage("正在刷新自动池...");
    try {
      const result = await refreshAutoPool();
      setMessage(`自动池刷新完成: ${JSON.stringify(result)}`);
      await loadPool();
    } catch (err) {
      setMessage(`自动池刷新失败: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onManualAdd() {
    if (!symbolInput.trim()) {
      setMessage("请输入 symbol");
      return;
    }

    setBusy(true);
    setMessage("处理中...");
    try {
      await manualAddSymbol(symbolInput.trim().toUpperCase());
      setSymbolInput("");
      setMessage("已添加到池子（初始化将由自动任务执行）");
      await loadPool();
    } catch (err) {
      setMessage(`添加失败: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  async function onManualRemove(symbol: string) {
    setBusy(true);
    setMessage(`移除 ${symbol} 中...`);
    try {
      await manualRemoveSymbol(symbol);
      setMessage(`已移除 ${symbol}`);
      await loadPool();
    } catch (err) {
      setMessage(`移除失败: ${(err as Error).message}`);
    } finally {
      setBusy(false);
    }
  }

  return (
    <main>
      <h1>标的池</h1>
      <p>总数: {items.length}，active: {activeCount}</p>

      <section className="panel">
        <h2>操作区</h2>
        <div className="row gap">
          <Link className="btn ghost" href="/tasks">任务页</Link>
          <button className="btn" disabled={busy} onClick={onRefreshAuto}>刷新自动池</button>
          <input
            className="input"
            placeholder="例如 1000PEPEUSDT"
            value={symbolInput}
            onChange={(e) => setSymbolInput(e.target.value)}
          />
          <button className="btn" disabled={busy} onClick={() => onManualAdd()}>手动添加</button>
        </div>
        <p className="msg">{message}</p>
      </section>

      <section className="panel">
        <h2>池子列表</h2>
        <div className="row gap" style={{ marginBottom: 10 }}>
          <select className="select" value={sectorFilter} onChange={(e) => setSectorFilter(e.target.value)}>
            <option value="all">Sector: 全部</option>
            <option value="-">Sector: 未分类</option>
            {sectorOptions.map((value) => (
              <option key={value} value={value}>{value}</option>
            ))}
          </select>
          <select className="select" value={tierFilter} onChange={(e) => setTierFilter(e.target.value)}>
            <option value="all">Tier: 全部</option>
            <option value="core">core（核心池）</option>
            <option value="tracked">tracked（历史池）</option>
            <option value="-">未定义</option>
          </select>
          <select className="select" value={statusFilter} onChange={(e) => setStatusFilter(e.target.value)}>
            <option value="all">Status: 全部</option>
            <option value="active">active（启用）</option>
            <option value="inactive">inactive（停用）</option>
          </select>
          <select className="select" value={sourceFilter} onChange={(e) => setSourceFilter(e.target.value)}>
            <option value="all">Source: 全部</option>
            <option value="auto">auto（自动）</option>
            <option value="manual">manual（手动）</option>
          </select>
          <span className="msg">筛选后: {filteredItems.length}</span>
        </div>
        {loading ? (
          <p>加载中...</p>
        ) : (
          <table className="table">
            <thead>
              <tr>
                <th>Symbol</th>
                <th>Sector</th>
                <th>Tier</th>
                <th>Status</th>
                <th>Source</th>
                <th>Updated</th>
                <th>Actions</th>
              </tr>
            </thead>
            <tbody>
              {filteredItems.map((row) => (
                <tr key={row.symbol}>
                  <td>
                    <Link href={`/symbol/${encodeURIComponent(row.symbol)}`}>{row.symbol}</Link>
                  </td>
                  <td>{row.sector ?? "-"}</td>
                  <td>{formatTierLabel(row.tier)}</td>
                  <td>{formatStatusLabel(row.status)}</td>
                  <td>{formatSourceLabel(row.source)}</td>
                  <td>{formatUtc8(row.updated_at)}</td>
                  <td>
                    <div className="row gap">
                      <button className="btn ghost" disabled={busy} onClick={() => onManualRemove(row.symbol)}>删除</button>
                    </div>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
        )}
      </section>
    </main>
  );
}

function formatTierLabel(value: string | null): string {
  if (value === "core") {
    return "core（核心池）";
  }
  if (value === "watch") {
    return "watch（历史池）";
  }
  if (value === "tracked") {
    return "tracked（历史池）";
  }
  return value ? `${value}（未定义）` : "-";
}

function formatStatusLabel(value: "active" | "inactive"): string {
  return value === "active" ? "active（启用）" : "inactive（停用）";
}

function formatSourceLabel(value: "auto" | "manual"): string {
  return value === "auto" ? "auto（自动）" : "manual（手动）";
}
