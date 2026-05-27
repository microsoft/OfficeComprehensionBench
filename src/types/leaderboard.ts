export type ModelId = string;

export interface ModelMeta {
  id: ModelId;
  display_name: string;
  org: string;
  color: string;
}

export interface FileTypeCombo {
  id: string;
  label: string;
}

export interface AblationMode {
  id: string;
  label: string;
}

export interface Metadata {
  benchmark_name: string;
  version: string;
  last_updated: string;
  description?: string;
  models: ModelMeta[];
  industries: string[];
  file_type_combos: FileTypeCombo[];
  fidelity_apps: string[];
  fidelity_sizes?: string[];
  human_baselines?: Record<string, number>;
}

export interface CIScore {
  mean: number;
  ci_low: number;
  ci_high: number;
  n?: number;
}

/** A row that has per-model CI scores plus optional n_queries / n_assertions */
export type CIRow = {
  n_queries?: number;
  n_assertions?: number;
} & Record<ModelId, CIScore | undefined>;

/** A row that has per-model plain numeric scores plus optional n_queries / n_assertions */
export type ScoreRow = {
  n_queries?: number;
  n_assertions?: number;
} & Record<ModelId, number | null | undefined>;

export interface DomainQnA {
  main: Record<ModelId, CIScore>;
  ablations: {
    gpt55_modes: AblationMode[];
    claude47_modes: AblationMode[];
  } & Record<ModelId, Record<string, CIScore>>;
  by_industry: Record<string, CIRow>;
  by_file_type: Record<string, CIRow>;
}

export interface FidelityMainEntry {
  score: number;
  n?: number;
}

export interface FidelityAppData {
  main: Record<ModelId, FidelityMainEntry>;
  by_feature: Record<string, ScoreRow>;
  by_size?: Record<string, ScoreRow>;
}

export interface FileFidelity {
  human_baseline: Record<string, number>;
  word: FidelityAppData;
  powerpoint: FidelityAppData;
  excel: FidelityAppData;
}

export interface Leaderboard {
  metadata: Metadata;
  domain_qna: DomainQnA;
  file_fidelity: FileFidelity;
}

/** Reserved keys that may live alongside per-model entries in a row. */
export const META_KEYS = new Set(['n_queries', 'n_assertions']);
