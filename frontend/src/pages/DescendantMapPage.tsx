import { useCallback, useEffect, useMemo, useRef, useState } from "react";
import { keepPreviousData, useQuery } from "@tanstack/react-query";
import {
  Background,
  BackgroundVariant,
  Controls,
  Edge,
  Handle,
  MiniMap,
  Node,
  NodeProps,
  Position,
  ReactFlow,
  ReactFlowProvider,
  useReactFlow,
  type OnMove
} from "@xyflow/react";
import { toPng } from "html-to-image";
import {
  Download,
  Eye,
  EyeOff,
  LocateFixed,
  Maximize2,
  Search,
  ZoomIn,
  ZoomOut
} from "lucide-react";
import { Navigate, useParams, useSearchParams } from "react-router-dom";
import { fetchDescendantViewport, searchMembers } from "../api";
import { useDebouncedValue } from "../hooks/useDebouncedValue";
import type {
  Bounds,
  DescendantMapNode,
  Genealogy,
  MemberSummary
} from "../types";

const initialBounds: Bounds = {
  x_min: -700,
  x_max: 1800,
  y_min: -900,
  y_max: 1400
};

type MemberFlowNode = Node<DescendantMapNode, "member">;

function yearText(node: Pick<DescendantMapNode, "birth_year" | "death_year">) {
  if (!node.birth_year && !node.death_year) {
    return "生卒未详";
  }
  return `${node.birth_year || "?"} - ${node.death_year || "?"}`;
}

function MemberNodeCard({ data, selected }: NodeProps<MemberFlowNode>) {
  return (
    <div className={`tree-node tree-node-${data.gender} ${selected ? "is-selected" : ""}`}>
      <Handle className="tree-handle" type="target" position={Position.Left} />
      <Handle className="tree-handle" type="source" position={Position.Right} />
      <div className="tree-node-head">
        <strong>{data.full_name}</strong>
        <span>G{data.depth}</span>
      </div>
      <div className="tree-node-meta">
        <span>#{data.member_id}</span>
        <span>{yearText(data)}</span>
      </div>
      {data.has_hidden_children ? (
        <div className="tree-node-foot">{data.child_count} 位子女 · 深度外</div>
      ) : (
        <div className="tree-node-foot">{data.child_count} 位子女</div>
      )}
    </div>
  );
}

const nodeTypes = {
  member: MemberNodeCard
};

function boundsFromViewport(
  viewport: { x: number; y: number; zoom: number },
  width: number,
  height: number
): Bounds {
  const zoom = viewport.zoom || 1;
  return {
    x_min: (-viewport.x - 80) / zoom,
    x_max: (width - viewport.x + 80) / zoom,
    y_min: (-viewport.y - 80) / zoom,
    y_max: (height - viewport.y + 80) / zoom
  };
}

function memberLabel(member: MemberSummary) {
  const years = member.birth_year || member.death_year
    ? ` · ${member.birth_year || "?"}-${member.death_year || "?"}`
    : "";
  return `#${member.member_id} ${member.full_name}${years}`;
}

function MapToolbar({
  showMiniMap,
  onToggleMiniMap,
  canvasRef
}: {
  showMiniMap: boolean;
  onToggleMiniMap: () => void;
  canvasRef: React.RefObject<HTMLDivElement | null>;
}) {
  const reactFlow = useReactFlow();

  const exportImage = useCallback(async () => {
    if (!canvasRef.current) {
      return;
    }
    const dataUrl = await toPng(canvasRef.current, {
      backgroundColor: "#f4f7f5",
      pixelRatio: 2,
      filter: (node) => !(node instanceof HTMLElement && node.classList.contains("no-export"))
    });
    const link = document.createElement("a");
    link.download = "descendant-map.png";
    link.href = dataUrl;
    link.click();
  }, [canvasRef]);

  return (
    <div className="map-toolbar no-export" aria-label="地图工具栏">
      <button type="button" title="放大" onClick={() => reactFlow.zoomIn({ duration: 160 })}>
        <ZoomIn size={18} />
      </button>
      <button type="button" title="缩小" onClick={() => reactFlow.zoomOut({ duration: 160 })}>
        <ZoomOut size={18} />
      </button>
      <button type="button" title="适配视图" onClick={() => reactFlow.fitView({ padding: 0.22, duration: 260 })}>
        <Maximize2 size={18} />
      </button>
      <button type="button" title="定位根节点" onClick={() => reactFlow.setCenter(0, 0, { zoom: 1.15, duration: 260 })}>
        <LocateFixed size={18} />
      </button>
      <button type="button" title="切换小地图" onClick={onToggleMiniMap}>
        {showMiniMap ? <EyeOff size={18} /> : <Eye size={18} />}
      </button>
      <button type="button" title="导出图片" onClick={exportImage}>
        <Download size={18} />
      </button>
    </div>
  );
}

function DescendantMapCanvas({
  genealogy,
  rootMember,
  maxDepth,
  onSelectedNodeChange
}: {
  genealogy: Genealogy;
  rootMember: MemberSummary;
  maxDepth: number;
  onSelectedNodeChange: (node: DescendantMapNode | null) => void;
}) {
  const canvasRef = useRef<HTMLDivElement>(null);
  const [bounds, setBounds] = useState<Bounds>(initialBounds);
  const [showMiniMap, setShowMiniMap] = useState(true);
  const debouncedBounds = useDebouncedValue(bounds, 180);
  const reactFlow = useReactFlow();

  const mapQuery = useQuery({
    queryKey: [
      "descendant-map",
      genealogy.genealogy_id,
      rootMember.member_id,
      maxDepth,
      Math.round(debouncedBounds.x_min),
      Math.round(debouncedBounds.x_max),
      Math.round(debouncedBounds.y_min),
      Math.round(debouncedBounds.y_max)
    ],
    queryFn: ({ signal }) =>
      fetchDescendantViewport(
        genealogy.genealogy_id,
        rootMember.member_id,
        maxDepth,
        debouncedBounds,
        signal
      ),
    placeholderData: keepPreviousData
  });

  const flowNodes = useMemo<MemberFlowNode[]>(() => {
    return (mapQuery.data?.nodes || []).map((node) => ({
      id: String(node.member_id),
      type: "member",
      position: node.position,
      data: node
    }));
  }, [mapQuery.data?.nodes]);

  const flowEdges = useMemo<Edge[]>(() => {
    return (mapQuery.data?.edges || []).map((edge) => ({
      id: edge.id,
      source: String(edge.source),
      target: String(edge.target),
      type: "smoothstep",
      className: "tree-edge"
    }));
  }, [mapQuery.data?.edges]);

  const updateBounds = useCallback((viewport: { x: number; y: number; zoom: number }) => {
    const rect = canvasRef.current?.getBoundingClientRect();
    if (!rect) {
      return;
    }
    setBounds(boundsFromViewport(viewport, rect.width, rect.height));
  }, []);

  const handleMove: OnMove = useCallback(
    (_event, viewport) => {
      updateBounds(viewport);
    },
    [updateBounds]
  );

  useEffect(() => {
    onSelectedNodeChange(null);
    window.setTimeout(() => {
      reactFlow.setCenter(0, 0, { zoom: 1.05, duration: 260 });
      updateBounds(reactFlow.getViewport());
    }, 0);
  }, [onSelectedNodeChange, reactFlow, rootMember.member_id, updateBounds]);

  useEffect(() => {
    if (flowNodes.length > 0) {
      window.setTimeout(() => reactFlow.fitView({ padding: 0.24, duration: 220 }), 0);
    }
  }, [flowNodes.length, reactFlow, rootMember.member_id]);

  return (
    <div className="map-canvas" ref={canvasRef}>
      <MapToolbar
        canvasRef={canvasRef}
        showMiniMap={showMiniMap}
        onToggleMiniMap={() => setShowMiniMap((value) => !value)}
      />
      <ReactFlow
        nodes={flowNodes}
        edges={flowEdges}
        nodeTypes={nodeTypes}
        fitView
        minZoom={0.16}
        maxZoom={2.2}
        defaultViewport={{ x: 80, y: 260, zoom: 0.95 }}
        onMove={handleMove}
        onMoveEnd={handleMove}
        onNodeClick={(_event, node) => onSelectedNodeChange(node.data)}
        onPaneClick={() => onSelectedNodeChange(null)}
        proOptions={{ hideAttribution: true }}
      >
        <Background
          color="#cfd8d2"
          gap={32}
          size={1.2}
          variant={BackgroundVariant.Dots}
        />
        <Controls className="flow-controls no-export" showInteractive={false} />
        {showMiniMap ? (
          <MiniMap
            className="flow-minimap no-export"
            nodeColor={(node) => {
              const data = node.data as DescendantMapNode;
              if (data.gender === "male") {
                return "#346d62";
              }
              if (data.gender === "female") {
                return "#9a5f70";
              }
              return "#777f77";
            }}
            maskColor="rgba(33, 41, 37, 0.1)"
          />
        ) : null}
      </ReactFlow>
      <div className="map-status no-export">
        {mapQuery.isFetching ? <span>正在加载视口</span> : <span>视口已同步</span>}
        {mapQuery.data ? (
          <span>
            {mapQuery.data.nodes.length}/{mapQuery.data.total_node_count} 节点
          </span>
        ) : null}
      </div>
      {mapQuery.isError ? (
        <div className="map-error no-export">{mapQuery.error.message}</div>
      ) : null}
    </div>
  );
}

function RootPicker({
  genealogy,
  selectedRoot,
  onSelectRoot
}: {
  genealogy: Genealogy;
  selectedRoot: MemberSummary | null;
  onSelectRoot: (member: MemberSummary) => void;
}) {
  const [query, setQuery] = useState("");
  const debouncedQuery = useDebouncedValue(query, 220);
  const membersQuery = useQuery({
    queryKey: ["member-search", genealogy.genealogy_id, debouncedQuery],
    queryFn: ({ signal }) => searchMembers(genealogy.genealogy_id, debouncedQuery, signal)
  });

  useEffect(() => {
    if (!selectedRoot && membersQuery.data?.members[0]) {
      onSelectRoot(membersQuery.data.members[0]);
    }
  }, [membersQuery.data?.members, onSelectRoot, selectedRoot]);

  return (
    <section className="side-section">
      <h2>根成员</h2>
      <label className="search-field">
        <Search size={16} />
        <input
          value={query}
          onChange={(event) => setQuery(event.target.value)}
          placeholder="姓名、分支或 ID"
        />
      </label>
      <div className="member-results">
        {(membersQuery.data?.members || []).map((member) => (
          <button
            type="button"
            key={member.member_id}
            className={selectedRoot?.member_id === member.member_id ? "is-active" : ""}
            onClick={() => onSelectRoot(member)}
          >
            {memberLabel(member)}
          </button>
        ))}
      </div>
    </section>
  );
}

function DetailDrawer({
  genealogyId,
  node
}: {
  genealogyId: number;
  node: DescendantMapNode | null;
}) {
  return (
    <aside className={`detail-drawer ${node ? "is-open" : ""}`} aria-live="polite">
      {node ? (
        <>
          <span className="drawer-label">成员详情</span>
          <h2>{node.full_name}</h2>
          <dl>
            <div>
              <dt>成员 ID</dt>
              <dd>{node.member_id}</dd>
            </div>
            <div>
              <dt>层级</dt>
              <dd>第 {node.depth} 代</dd>
            </div>
            <div>
              <dt>生卒</dt>
              <dd>{yearText(node)}</dd>
            </div>
            <div>
              <dt>子女</dt>
              <dd>{node.child_count}</dd>
            </div>
          </dl>
          <a
            className="secondary-link"
            href={`/genealogies/${genealogyId}/members/${node.member_id}/`}
          >
            打开成员档案
          </a>
        </>
      ) : (
        <>
          <span className="drawer-label">成员详情</span>
          <h2>未选择节点</h2>
          <p>暂无成员上下文。</p>
        </>
      )}
    </aside>
  );
}

export function DescendantMapPage({ genealogies }: { genealogies: Genealogy[] }) {
  const params = useParams();
  const [searchParams, setSearchParams] = useSearchParams();
  const genealogyId = Number(params.genealogyId);
  const genealogy = genealogies.find((item) => item.genealogy_id === genealogyId);
  const [selectedRoot, setSelectedRoot] = useState<MemberSummary | null>(null);
  const [selectedNode, setSelectedNode] = useState<DescendantMapNode | null>(null);
  const [maxDepth, setMaxDepth] = useState(6);
  const initialRoot = searchParams.get("root") || "";

  const initialRootQuery = useQuery({
    queryKey: ["member-search", genealogyId, initialRoot],
    queryFn: ({ signal }) => searchMembers(genealogyId, initialRoot, signal),
    enabled: Boolean(genealogy && initialRoot)
  });

  useEffect(() => {
    if (!selectedRoot && initialRootQuery.data?.members[0]) {
      setSelectedRoot(initialRootQuery.data.members[0]);
    }
  }, [initialRootQuery.data?.members, selectedRoot]);

  const handleSelectRoot = useCallback(
    (member: MemberSummary) => {
      setSelectedRoot(member);
      setSearchParams({ root: String(member.member_id) }, { replace: true });
    },
    [setSearchParams]
  );

  if (!genealogy) {
    return <Navigate to="/" replace />;
  }

  return (
    <ReactFlowProvider>
      <section className="map-workspace">
        <aside className="map-side">
          <div className="side-title">
            <span>{genealogy.surname.slice(0, 1)}</span>
            <div>
              <h1>{genealogy.title}</h1>
              <p>后代地图 · {genealogy.member_count} 成员</p>
            </div>
          </div>
          <RootPicker
            genealogy={genealogy}
            selectedRoot={selectedRoot}
            onSelectRoot={handleSelectRoot}
          />
          <section className="side-section">
            <h2>深度</h2>
            <div className="depth-control">
              <input
                type="range"
                min={1}
                max={30}
                value={maxDepth}
                onChange={(event) => setMaxDepth(Number(event.target.value))}
              />
              <output>{maxDepth} 代</output>
            </div>
          </section>
          <section className="side-section side-summary">
            <h2>谱牒概况</h2>
            <dl>
              <div>
                <dt>成员</dt>
                <dd>{genealogy.member_count}</dd>
              </div>
              <div>
                <dt>关系</dt>
                <dd>{genealogy.relation_count}</dd>
              </div>
            </dl>
          </section>
          <section className="side-section side-links">
            <h2>维护入口</h2>
            <a href={`/genealogies/${genealogy.genealogy_id}/members/`}>成员管理</a>
            <a href={`/genealogies/${genealogy.genealogy_id}/relationships/`}>关系维护</a>
            <a href={`/genealogies/${genealogy.genealogy_id}/analytics/`}>统计分析</a>
          </section>
        </aside>

        <div className="map-stage">
          {selectedRoot ? (
            <DescendantMapCanvas
              genealogy={genealogy}
              rootMember={selectedRoot}
              maxDepth={maxDepth}
              onSelectedNodeChange={setSelectedNode}
            />
          ) : (
            <div className="surface-state">
              <div className="spinner" />
              <span>正在查找根成员</span>
            </div>
          )}
        </div>
        <DetailDrawer genealogyId={genealogy.genealogy_id} node={selectedNode} />
      </section>
    </ReactFlowProvider>
  );
}
