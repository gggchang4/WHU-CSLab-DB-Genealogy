export type Genealogy = {
  genealogy_id: number;
  title: string;
  surname: string;
  compiled_at: number | null;
  description: string;
  owner_name: string;
  member_count: number;
  relation_count: number;
  role: "owner" | "editor" | "viewer";
};

export type MemberSummary = {
  member_id: number;
  full_name: string;
  gender: "male" | "female" | "unknown";
  birth_year: number | null;
  death_year: number | null;
  generation_label: string;
  branch_name: string;
};

export type Bounds = {
  x_min: number;
  x_max: number;
  y_min: number;
  y_max: number;
};

export type DescendantMapNode = {
  member_id: number;
  full_name: string;
  gender: "male" | "female" | "unknown";
  birth_year: number | null;
  death_year: number | null;
  depth: number;
  position: { x: number; y: number };
  child_count: number;
  has_hidden_children: boolean;
};

export type DescendantMapEdge = {
  id: string;
  source: number;
  target: number;
};

export type DescendantMapResponse = {
  nodes: DescendantMapNode[];
  edges: DescendantMapEdge[];
  layout_bounds: Bounds;
  loaded_bounds: Bounds;
  total_node_count: number;
  has_more: boolean;
};

export type BenchmarkPlanSide = {
  execution_time_ms: number | null;
  planning_time_ms: number | null;
  scan_types: string[];
  top_node: string;
  plan: string;
};

export type ParentLookupBenchmarkResponse = {
  genealogy_id: number;
  root_member_id: number;
  query_name: string;
  sql: string;
  index_names: string[];
  with_index: BenchmarkPlanSide;
  without_index: BenchmarkPlanSide;
  speedup_ratio: number | null;
  method: string;
};
