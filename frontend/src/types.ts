export interface GraphNode {
  id: string;
  label: string;
  depth: number;
}

export interface GraphEdge {
  source: string;
  target: string;
}

export interface GraphData {
  nodes: GraphNode[];
  edges: GraphEdge[];
}

export interface GenerateRequest {
  seeds: string[];
  iterations: number;
  max_concepts?: number;
  temperature?: number;
}
