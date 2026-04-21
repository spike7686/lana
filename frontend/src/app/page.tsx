import Link from "next/link";

export default function HomePage() {
  return (
    <main>
      <h1>Lana Project</h1>
      <p>历史仓库与指标分析面板</p>

      <section className="panel">
        <h2>导航</h2>
        <div className="row gap">
          <Link href="/pool" className="btn">进入标的池</Link>
          <Link href="/tasks" className="btn ghost">任务监控</Link>
        </div>
      </section>
    </main>
  );
}
