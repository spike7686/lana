"use client";

import { useEffect, useMemo, useRef, useState } from "react";
import {
  ColorType,
  createChart,
  type CandlestickData,
  type HistogramData,
  type IChartApi,
  type ISeriesApi,
  type LineData,
  type UTCTimestamp,
} from "lightweight-charts";

import type { KlinePoint, OIPoint } from "@/lib/api";

function toUtcTimestamp(value: string): UTCTimestamp {
  return Math.floor(new Date(value).getTime() / 1000) as UTCTimestamp;
}

export function SymbolCharts({
  kline,
  oi,
}: {
  kline: KlinePoint[];
  oi: OIPoint[];
}) {
  const [showCandles, setShowCandles] = useState(true);
  const [showOI, setShowOI] = useState(true);
  const [showVolume, setShowVolume] = useState(true);
  const containerRef = useRef<HTMLDivElement | null>(null);

  const candleData = useMemo<CandlestickData[]>(() => {
    return kline.map((row) => ({
      time: toUtcTimestamp(row.open_time),
      open: row.open,
      high: row.high,
      low: row.low,
      close: row.close,
    }));
  }, [kline]);

  const oiData = useMemo<LineData[]>(() => {
    return oi
      .filter((row) => row.sum_open_interest !== null || row.sum_open_interest_value !== null)
      .map((row) => ({
        time: toUtcTimestamp(row.ts),
        value:
          row.sum_open_interest_value !== null
            ? row.sum_open_interest_value
            : (row.sum_open_interest as number),
      }));
  }, [oi]);

  const volumeData = useMemo<HistogramData[]>(() => {
    return kline.map((row) => ({
      time: toUtcTimestamp(row.open_time),
      value: row.volume,
      color: row.close >= row.open ? "rgba(22, 163, 74, 0.55)" : "rgba(220, 38, 38, 0.55)",
    }));
  }, [kline]);

  useEffect(() => {
    if (!containerRef.current) {
      return;
    }

    const container = containerRef.current;
    const chart: IChartApi = createChart(container, {
      width: container.clientWidth,
      height: container.clientHeight || 520,
      layout: {
        background: { type: ColorType.Solid, color: "#ffffff" },
        textColor: "#0f172a",
      },
      grid: {
        vertLines: { color: "#eef2ff" },
        horzLines: { color: "#eef2ff" },
      },
      rightPriceScale: { borderColor: "#cbd5e1" },
      leftPriceScale: { visible: true, borderColor: "#cbd5e1" },
      overlayPriceScales: { borderColor: "#cbd5e1" },
      timeScale: { borderColor: "#cbd5e1", timeVisible: true, secondsVisible: false },
      crosshair: { mode: 1 },
    });

    if (showCandles) {
      const series: ISeriesApi<"Candlestick"> = chart.addCandlestickSeries({
        upColor: "#16a34a",
        downColor: "#dc2626",
        borderVisible: false,
        wickUpColor: "#16a34a",
        wickDownColor: "#dc2626",
      });
      series.setData(candleData);
    }

    if (showOI) {
      const line: ISeriesApi<"Line"> = chart.addLineSeries({
        color: "#2563eb",
        lineWidth: 2,
        priceLineVisible: false,
        lastValueVisible: true,
        priceScaleId: "left",
      });
      line.setData(oiData);
    }

    if (showVolume) {
      const volume: ISeriesApi<"Histogram"> = chart.addHistogramSeries({
        priceScaleId: "",
        priceFormat: { type: "volume" },
        lastValueVisible: false,
        priceLineVisible: false,
      });
      volume.setData(volumeData);
      chart.priceScale("").applyOptions({
        scaleMargins: { top: 0.78, bottom: 0 },
      });
      chart.priceScale("left").applyOptions({
        scaleMargins: { top: 0.1, bottom: 0.28 },
      });
      chart.priceScale("right").applyOptions({
        scaleMargins: { top: 0.1, bottom: 0.28 },
      });
    } else {
      chart.priceScale("left").applyOptions({
        scaleMargins: { top: 0.1, bottom: 0.1 },
      });
      chart.priceScale("right").applyOptions({
        scaleMargins: { top: 0.1, bottom: 0.1 },
      });
    }

    chart.timeScale().fitContent();

    const resizeObserver = new ResizeObserver(() => {
      chart.applyOptions({
        width: container.clientWidth,
        height: container.clientHeight || 520,
      });
    });
    resizeObserver.observe(container);

    return () => {
      resizeObserver.disconnect();
      chart.remove();
    };
  }, [candleData, oiData, volumeData, showCandles, showOI, showVolume]);

  return (
    <div className="charts-wrap">
      <div className="chart-frame">
        <div className="chart-controls">
          <button
            className={`icon-btn ${showCandles ? "active" : ""}`}
            onClick={() => setShowCandles((v) => !v)}
            title={showCandles ? "隐藏K线" : "显示K线"}
          >
            <EyeIcon off={!showCandles} />
            <span>K线</span>
          </button>
          <button
            className={`icon-btn ${showOI ? "active" : ""}`}
            onClick={() => setShowOI((v) => !v)}
            title={showOI ? "隐藏OI" : "显示OI"}
          >
            <EyeIcon off={!showOI} />
            <span>OI</span>
          </button>
          <button
            className={`icon-btn ${showVolume ? "active" : ""}`}
            onClick={() => setShowVolume((v) => !v)}
            title={showVolume ? "隐藏量" : "显示量"}
          >
            <EyeIcon off={!showVolume} />
            <span>量</span>
          </button>
        </div>
        <h3>K线 + OI + 成交量</h3>
        <div ref={containerRef} className="chart-box" />
      </div>
    </div>
  );
}

function EyeIcon({ off }: { off: boolean }) {
  return off ? (
    <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
      <path
        d="M3 3l18 18M10.6 10.6a2 2 0 102.8 2.8M9.9 5.1A11.3 11.3 0 0112 5c5.5 0 9.5 4.3 10.7 6.1a1.7 1.7 0 010 1.8 17.5 17.5 0 01-4.1 4.3M6.1 6.1A17.5 17.5 0 001.3 11a1.7 1.7 0 000 1.8C2.5 14.6 6.5 19 12 19c1.4 0 2.7-.3 3.9-.8"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
      />
    </svg>
  ) : (
    <svg viewBox="0 0 24 24" width="14" height="14" aria-hidden="true">
      <path
        d="M1.3 12a1.7 1.7 0 010-1.8C2.5 8.4 6.5 4 12 4s9.5 4.4 10.7 6.2a1.7 1.7 0 010 1.8C21.5 13.8 17.5 18 12 18S2.5 13.8 1.3 12z"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
      />
      <circle cx="12" cy="11" r="3" fill="none" stroke="currentColor" strokeWidth="2" />
    </svg>
  );
}
