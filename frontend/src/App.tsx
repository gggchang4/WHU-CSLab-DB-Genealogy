import { useCallback, useMemo, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BarChart3,
  ChevronRight,
  Database,
  FileDown,
  GitBranch,
  LayoutDashboard,
  LogOut,
  Map,
  Network,
  Plus,
  Search,
  ShieldCheck,
  Users
} from "lucide-react";
import { Link, Navigate, Route, Routes, useParams } from "react-router-dom";
import { fetchGenealogies, logout } from "./api";
import { DescendantMapPage } from "./pages/DescendantMapPage";
import type { Genealogy } from "./types";

function roleLabel(role: Genealogy["role"]) {
  if (role === "owner") {
    return "所有者";
  }
  if (role === "editor") {
    return "编辑者";
  }
  return "只读";
}

function formatNumber(value: number) {
  return value.toLocaleString("zh-CN");
}

const prefetchedDocuments = new Set<string>();

function shouldPrefetchDocument(url: URL) {
  return !url.pathname.includes("/relationships/") && !url.pathname.includes("/analytics/");
}

function prefetchDocument(href?: string) {
  if (!href || typeof window === "undefined") {
    return;
  }

  const url = new URL(href, window.location.href);
  if (
    url.origin !== window.location.origin ||
    !shouldPrefetchDocument(url) ||
    prefetchedDocuments.has(url.href)
  ) {
    return;
  }

  prefetchedDocuments.add(url.href);
  const link = document.createElement("link");
  link.rel = "prefetch";
  link.as = "document";
  link.href = url.href;
  document.head.appendChild(link);
}

function AppShell({ children }: { children: React.ReactNode }) {
  const [isLoggingOut, setIsLoggingOut] = useState(false);

  const handleLogout = useCallback(async () => {
    setIsLoggingOut(true);
    await logout();
  }, []);

  return (
    <div className="app-frame">
      <aside className="app-rail" aria-label="主导航">
        <Link className="brand-lockup" to="/">
          <span className="brand-seal">谱</span>
          <span>
            <strong>寻根溯源</strong>
            <small>族谱工作台</small>
          </span>
        </Link>

        <nav className="rail-nav">
          <Link to="/" className="rail-link">
            <LayoutDashboard size={18} />
            <span>工作台</span>
          </Link>
          <a href="/genealogies/new/" className="rail-link">
            <Plus size={18} />
            <span>新建族谱</span>
          </a>
        </nav>

        <div className="rail-foot">
          <span className="rail-status">当前会话</span>
          <button
            type="button"
            className="logout-button"
            onClick={handleLogout}
            disabled={isLoggingOut}
          >
            <LogOut size={17} />
            <span>{isLoggingOut ? "退出中" : "退出登录"}</span>
          </button>
        </div>
      </aside>
      <main className="app-main">{children}</main>
    </div>
  );
}

function LoadingSurface() {
  return (
    <div className="surface-state">
      <div className="spinner" />
      <span>正在载入族谱数据</span>
    </div>
  );
}

function ErrorSurface({ message }: { message: string }) {
  return (
    <div className="surface-state surface-state-error">
      <span>{message}</span>
      <a href="/accounts/login/">重新登录</a>
    </div>
  );
}

function MetricLine({
  label,
  value,
  detail
}: {
  label: string;
  value: string;
  detail: string;
}) {
  return (
    <div className="metric-line">
      <span>{label}</span>
      <strong>{value}</strong>
      <small>{detail}</small>
    </div>
  );
}

function ActionLink({
  href,
  to,
  icon,
  label,
  detail,
  primary = false
}: {
  href?: string;
  to?: string;
  icon: React.ReactNode;
  label: string;
  detail: string;
  primary?: boolean;
}) {
  const className = primary ? "action-row action-row-primary" : "action-row";
  const content = (
    <>
      <span className="action-icon">{icon}</span>
      <span>
        <strong>{label}</strong>
        <small>{detail}</small>
      </span>
      <ChevronRight size={17} />
    </>
  );

  if (to) {
    return (
      <Link className={className} to={to}>
        {content}
      </Link>
    );
  }

  return (
    <a
      className={className}
      href={href}
      onFocus={() => prefetchDocument(href)}
      onMouseEnter={() => prefetchDocument(href)}
    >
      {content}
    </a>
  );
}

function GenealogyList({
  genealogies,
  selectedGenealogy,
  onSelect
}: {
  genealogies: Genealogy[];
  selectedGenealogy: Genealogy | null;
  onSelect: (genealogyId: number) => void;
}) {
  return (
    <section className="registry-panel" aria-label="族谱索引">
      <div className="panel-heading">
        <h2>族谱</h2>
        <a href="/genealogies/new/" title="新建族谱">
          <Plus size={18} />
        </a>
      </div>
      <div className="registry-list">
        {genealogies.map((genealogy) => (
          <button
            type="button"
            key={genealogy.genealogy_id}
            className={
              selectedGenealogy?.genealogy_id === genealogy.genealogy_id
                ? "registry-item is-active"
                : "registry-item"
            }
            onClick={() => onSelect(genealogy.genealogy_id)}
          >
            <span className="registry-seal">{genealogy.surname.slice(0, 1)}</span>
            <span className="registry-copy">
              <strong>{genealogy.title}</strong>
              <small>
                {formatNumber(genealogy.member_count)} 成员 ·{" "}
                {formatNumber(genealogy.relation_count)} 关系
              </small>
            </span>
            <span className={`role-chip role-${genealogy.role}`}>
              {roleLabel(genealogy.role)}
            </span>
          </button>
        ))}
      </div>
    </section>
  );
}

function GenealogyControlPanel({ genealogy }: { genealogy: Genealogy }) {
  const canEditGenealogy = genealogy.role === "owner" || genealogy.role === "editor";

  return (
    <section className="control-panel" aria-label="族谱操作">
      <div className="selected-head">
        <span className="selected-seal">{genealogy.surname.slice(0, 1)}</span>
        <div>
          <h2>{genealogy.title}</h2>
          <p>
            {genealogy.surname} 氏 · {roleLabel(genealogy.role)} · {genealogy.owner_name}
          </p>
        </div>
      </div>

      <div className="selected-metrics">
        <MetricLine
          label="成员"
          value={formatNumber(genealogy.member_count)}
          detail="可检索档案"
        />
        <MetricLine
          label="关系"
          value={formatNumber(genealogy.relation_count)}
          detail="亲缘连边"
        />
        <MetricLine
          label="编修"
          value={genealogy.compiled_at ? String(genealogy.compiled_at) : "-"}
          detail="谱牒年份"
        />
      </div>

      <div className="action-grid">
        <ActionLink
          primary
          to={`/genealogies/${genealogy.genealogy_id}/map`}
          icon={<Map size={18} />}
          label="后代地图"
          detail="拖拽、缩放、视口加载"
        />
        <ActionLink
          href={`/genealogies/${genealogy.genealogy_id}/members/`}
          icon={<Users size={18} />}
          label="成员管理"
          detail="成员增删改查与模糊检索"
        />
        <ActionLink
          href={`/genealogies/${genealogy.genealogy_id}/relationships/`}
          icon={<GitBranch size={18} />}
          label="关系维护"
          detail={canEditGenealogy ? "亲子关系与婚姻关系" : "只读查看亲子与婚姻关系"}
        />
        <ActionLink
          href={`/genealogies/${genealogy.genealogy_id}/queries/member/`}
          icon={<Search size={18} />}
          label="成员查询"
          detail="祖先追溯与亲缘路径"
        />
        <ActionLink
          href={`/genealogies/${genealogy.genealogy_id}/analytics/`}
          icon={<BarChart3 size={18} />}
          label="统计分析"
          detail="男女比例、寿命代际、SQL 结果"
        />
        <ActionLink
          href={`/genealogies/${genealogy.genealogy_id}/collaboration/`}
          icon={<ShieldCheck size={18} />}
          label="协作权限"
          detail="邀请、授权、角色维护"
        />
      </div>
    </section>
  );
}

function CourseworkPanel({ totals }: { totals: { genealogies: number; members: number; relations: number } }) {
  return (
    <section className="coursework-panel" aria-label="课程验收">
      <div>
        <h2>课程验收</h2>
        <p>围绕大规模数据、递归查询、COPY 导入导出和索引性能对比组织演示。</p>
      </div>
      <div className="coursework-grid">
        <div>
          <Database size={18} />
          <strong>{formatNumber(totals.members)}</strong>
          <span>系统成员</span>
        </div>
        <div>
          <Network size={18} />
          <strong>30 代</strong>
          <span>链路深度目标</span>
        </div>
        <div>
          <FileDown size={18} />
          <strong>COPY</strong>
          <span>导入导出材料</span>
        </div>
      </div>
    </section>
  );
}

function DashboardPage({ genealogies }: { genealogies: Genealogy[] }) {
  const [selectedId, setSelectedId] = useState<number | null>(null);
  const totals = useMemo(
    () =>
      genealogies.reduce(
        (acc, genealogy) => ({
          genealogies: acc.genealogies + 1,
          members: acc.members + genealogy.member_count,
          relations: acc.relations + genealogy.relation_count
        }),
        { genealogies: 0, members: 0, relations: 0 }
      ),
    [genealogies]
  );
  const selectedGenealogy =
    genealogies.find((genealogy) => genealogy.genealogy_id === selectedId) ??
    genealogies[0] ??
    null;
  const largestGenealogy = genealogies.reduce<Genealogy | null>(
    (largest, genealogy) =>
      !largest || genealogy.member_count > largest.member_count ? genealogy : largest,
    null
  );

  return (
    <section className="workspace">
      <header className="workspace-top">
        <div>
          <h1>族谱工作台</h1>
          <p>以成员 ID 和亲缘边为核心，浏览、维护并演示大规模族谱数据。</p>
        </div>
        <div className="top-stat-strip" aria-label="总览指标">
          <span>{formatNumber(totals.genealogies)} 部族谱</span>
          <span>{formatNumber(totals.members)} 位成员</span>
          <span>{formatNumber(totals.relations)} 条关系</span>
        </div>
      </header>

      {genealogies.length === 0 ? (
        <div className="empty-panel">
          <h2>当前账号还没有可访问的族谱</h2>
          <a href="/genealogies/new/">新建第一部族谱</a>
        </div>
      ) : (
        <div className="workbench-grid">
          <GenealogyList
            genealogies={genealogies}
            selectedGenealogy={selectedGenealogy}
            onSelect={setSelectedId}
          />
          <div className="workbench-main">
            {selectedGenealogy ? <GenealogyControlPanel genealogy={selectedGenealogy} /> : null}
            <div className="insight-band">
              <div>
                <span>最大数据集</span>
                <strong>{largestGenealogy?.title ?? "-"}</strong>
                <small>{formatNumber(largestGenealogy?.member_count ?? 0)} 位成员</small>
              </div>
              <div>
                <span>权限模型</span>
                <strong>创建者 / 编辑者 / 只读</strong>
                <small>仅展示可访问族谱</small>
              </div>
            </div>
            <CourseworkPanel totals={totals} />
          </div>
        </div>
      )}
    </section>
  );
}

function GenealogyDetailPage({ genealogies }: { genealogies: Genealogy[] }) {
  const params = useParams();
  const genealogyId = Number(params.genealogyId);
  const genealogy = genealogies.find((item) => item.genealogy_id === genealogyId);

  if (!genealogy) {
    return <Navigate to="/" replace />;
  }

  return (
    <section className="workspace detail-workspace">
      <header className="workspace-top">
        <div>
          <h1>{genealogy.title}</h1>
          <p>
            {genealogy.surname} 氏 · {roleLabel(genealogy.role)} · {genealogy.owner_name}
          </p>
        </div>
        <Link to={`/genealogies/${genealogy.genealogy_id}/map`} className="primary-command">
          <Map size={18} />
          <span>打开后代地图</span>
        </Link>
      </header>
      <GenealogyControlPanel genealogy={genealogy} />
    </section>
  );
}

function RoutedApp() {
  const genealogiesQuery = useQuery({
    queryKey: ["genealogies"],
    queryFn: ({ signal }) => fetchGenealogies(signal)
  });

  if (genealogiesQuery.isLoading) {
    return <LoadingSurface />;
  }

  if (genealogiesQuery.isError) {
    return <ErrorSurface message={genealogiesQuery.error.message} />;
  }

  const genealogies = genealogiesQuery.data?.genealogies ?? [];

  return (
    <Routes>
      <Route path="/" element={<DashboardPage genealogies={genealogies} />} />
      <Route
        path="/genealogies/:genealogyId"
        element={<GenealogyDetailPage genealogies={genealogies} />}
      />
      <Route
        path="/genealogies/:genealogyId/map"
        element={<DescendantMapPage genealogies={genealogies} />}
      />
      <Route path="*" element={<Navigate to="/" replace />} />
    </Routes>
  );
}

export function App() {
  return (
    <AppShell>
      <RoutedApp />
    </AppShell>
  );
}
