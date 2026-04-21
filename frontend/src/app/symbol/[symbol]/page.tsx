"use client";

import Link from "next/link";
import { useParams } from "next/navigation";
import { useEffect, useMemo, useState } from "react";

import {
  exportUrl,
  fetchKline,
  fetchOI,
  fetchProfile,
  type AssetProfile,
  type KlinePoint,
  type OIPoint,
} from "@/lib/api";
import { SymbolCharts } from "@/components/symbol-charts";
import { formatUtc8 } from "@/lib/time";

type Interval = "15m" | "1h";

export default function SymbolDetailPage() {
  const params = useParams<{ symbol: string }>();
  const symbol = decodeURIComponent(params.symbol ?? "").toUpperCase();

  const [interval, setInterval] = useState<Interval>("15m");
  const [kline, setKline] = useState<KlinePoint[]>([]);
  const [profile, setProfile] = useState<AssetProfile | null>(null);
  const [oi, setOi] = useState<OIPoint[]>([]);
  const [loading, setLoading] = useState(true);
  const [profileBusy, setProfileBusy] = useState(false);
  const [message, setMessage] = useState("");

  useEffect(() => {
    async function load() {
      setLoading(true);
      try {
        const [k, o] = await Promise.all([
          fetchKline(symbol, interval, 200),
          fetchOI(symbol, interval, 200),
        ]);
        setKline(k);
        setOi(o);
        const p = await fetchProfile(symbol, false);
        setProfile(p);
        setMessage("");
      } catch (err) {
        setMessage(`加载失败: ${(err as Error).message}`);
      } finally {
        setLoading(false);
      }
    }

    if (symbol) {
      void load();
    }
  }, [symbol, interval]);

  const latest = useMemo(() => {
    if (!kline.length) {
      return null;
    }
    return kline[kline.length - 1];
  }, [kline]);

  async function onRefreshProfile() {
    setProfileBusy(true);
    try {
      const p = await fetchProfile(symbol, true);
      setProfile(p);
      setMessage("项目简介已刷新");
    } catch (err) {
      setMessage(`刷新资料失败: ${(err as Error).message}`);
    } finally {
      setProfileBusy(false);
    }
  }

  return (
    <main>
      <h1>{symbol}</h1>
      <div className="row gap">
        <Link href="/pool" className="btn ghost">返回池子</Link>
        <button className="btn" onClick={() => setInterval("15m")} disabled={interval === "15m"}>15m</button>
        <button className="btn" onClick={() => setInterval("1h")} disabled={interval === "1h"}>1h</button>
        <a className="btn ghost" href={exportUrl(symbol, interval, "kline")} target="_blank" rel="noreferrer">下载CSV（K线+OI）</a>
      </div>

      {latest && (
        <section className="panel">
          <h2>最新K线</h2>
          <p>
            时间: {formatUtc(latest.open_time)} | O: {latest.open} H: {latest.high} L: {latest.low} C: {latest.close}
          </p>
        </section>
      )}

      <section className="panel">
        <h2>图表 ({interval})</h2>
        {loading ? (
          <p>加载中...</p>
        ) : (
          <SymbolCharts kline={kline} oi={oi} />
        )}
      </section>

      <section className="panel">
        <div className="row gap">
          <h2>项目简介</h2>
          <button className="btn ghost" disabled={profileBusy} onClick={onRefreshProfile}>
            {profileBusy ? "刷新中..." : "刷新资料"}
          </button>
        </div>
        {profile ? (
          <div className="profile-box">
            <p><strong>名称：</strong>{profile.name ?? "-"}</p>
            <p><strong>赛道：</strong>{profile.sector ?? "-"}</p>
            <p>
              <strong>官网：</strong>
              {profile.website ? (
                <a href={profile.website} target="_blank" rel="noreferrer">{profile.website}</a>
              ) : "-"}
            </p>
            <p>
              <strong>Twitter：</strong>
              {profile.twitter ? (
                <a href={profile.twitter} target="_blank" rel="noreferrer">{profile.twitter}</a>
              ) : "-"}
            </p>
            <p><strong>更新时间：</strong>{formatUtc(profile.updated_at)}</p>
            <p><strong>简介：</strong>{profile.description ?? "暂无描述"}</p>
          </div>
        ) : (
          <p>暂无项目资料</p>
        )}
      </section>

      {message ? <p className="msg">{message}</p> : null}
    </main>
  );
}

function formatUtc(value: string): string {
  return formatUtc8(value);
}
