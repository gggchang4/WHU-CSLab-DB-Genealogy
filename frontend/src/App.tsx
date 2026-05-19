import { useMemo } from "react";
import { useQuery } from "@tanstack/react-query";
import {
  BookOpen,
  ChevronRight,
  GitBranch,
  LayoutDashboard,
  Map,
  Search
} from "lucide-react";
import { Link, Navigate, Route, Routes, useParams } from "react-router-dom";
import { fetchGenealogies } from "./api";
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

function AppShell({ children }: { children: React.ReactNode }) {
  return (
    <div className="app-frame">
      <aside className="app-sidebar" aria-label="主导航">
        <Link className="brand-lockup" to="/">
          <span className="brand-mark">谱</span>
          <span>
            <strong>寻根溯源</strong>
            <small>Genealogy Map</small>
          </span>
        </Link>
        <nav className="nav-stack">
          <Link to="/" className="nav-item">
            <LayoutDashboard size={18} />
            <span>族谱总览</span>
          </Link>
          <a href="/" className="nav-item">
            <BookOpen size={18} />
            <span>旧版页面</span>
          </a>
        </nav>
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

function DashboardPage({ genealogies }: { genealogies: Genealogy[] }) {
  const totals = useMemo(
    () =>
      genealogies.reduce(
        (acc, genealogy) => ({
          members: acc.members + genealogy.member_count,
          relations: acc.relations + genealogy.relation_count
        }),
        { members: 0, relations: 0 }
      ),
    [genealogies]
  );

  return (
    <section className="workspace">
      <header className="workspace-header">
        <div>
          <h1>族谱工作台</h1>
          <p>选择一个族谱进入详情，或直接打开地图式后代视图。</p>
        </div>
        <div className="header-metrics" aria-label="总览指标">
          <span>{genealogies.length} 部族谱</span>
          <span>{totals.members} 位成员</span>
          <span>{totals.relations} 条亲缘边</span>
        </div>
      </header>

      {genealogies.length === 0 ? (
        <div className="empty-panel">当前账号还没有可访问的族谱。</div>
      ) : (
        <div className="genealogy-grid">
          {genealogies.map((genealogy) => (
            <article className="genealogy-card" key={genealogy.genealogy_id}>
              <div className="genealogy-card-main">
                <div>
                  <span className="card-kicker">{roleLabel(genealogy.role)}</span>
                  <h2>{genealogy.title}</h2>
                </div>
                <span className="surname-seal">{genealogy.surname.slice(0, 1)}</span>
              </div>
              <p>{genealogy.description || "暂无描述"}</p>
              <dl className="meta-row">
                <div>
                  <dt>成员</dt>
                  <dd>{genealogy.member_count}</dd>
                </div>
                <div>
                  <dt>关系</dt>
                  <dd>{genealogy.relation_count}</dd>
                </div>
                <div>
                  <dt>编修</dt>
                  <dd>{genealogy.compiled_at || "-"}</dd>
                </div>
              </dl>
              <div className="card-actions">
                <Link to={`/genealogies/${genealogy.genealogy_id}`} className="text-link">
                  详情入口
                  <ChevronRight size={16} />
                </Link>
                <Link
                  to={`/genealogies/${genealogy.genealogy_id}/map`}
                  className="primary-link"
                >
                  <Map size={16} />
                  后代地图
                </Link>
              </div>
            </article>
          ))}
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
    <section className="workspace detail-layout">
      <header className="workspace-header compact">
        <div>
          <h1>{genealogy.title}</h1>
          <p>{genealogy.surname} 氏 · {roleLabel(genealogy.role)} · {genealogy.owner_name}</p>
        </div>
        <Link to={`/genealogies/${genealogy.genealogy_id}/map`} className="primary-link">
          <Map size={17} />
          打开后代地图
        </Link>
      </header>
      <div className="detail-band">
        <div>
          <GitBranch size={26} />
          <h2>关系结构</h2>
          <p>当前首版 SPA 聚焦后代树浏览，成员档案、关系维护和协作管理继续保留在 Django 模板中。</p>
        </div>
        <div className="detail-actions">
          <a href={`/genealogies/${genealogy.genealogy_id}/members/`} className="secondary-link">
            成员列表
          </a>
          <a href={`/genealogies/${genealogy.genealogy_id}/relationships/`} className="secondary-link">
            关系管理
          </a>
          <a href={`/genealogies/${genealogy.genealogy_id}/analytics/`} className="secondary-link">
            统计页
          </a>
        </div>
      </div>
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
