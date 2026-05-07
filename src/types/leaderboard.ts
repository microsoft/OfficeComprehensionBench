export interface Score {
  raw: number
  percentage: number
  n?: number
}

export interface ModelInfo {
  id: string
  display_name: string
  org: string
  url?: string | null
}

export type ModelScoreMap = Record<string, Score>

export interface FileTypeBreakdown {
  word: ModelScoreMap
  powerpoint: ModelScoreMap
  excel: ModelScoreMap
  multifile: ModelScoreMap
  all_apps: ModelScoreMap
}

export interface DomainQnASection {
  overall: FileTypeBreakdown
  by_domain: Record<string, ModelScoreMap>
  by_file_type_and_domain: Record<string, Record<string, ModelScoreMap>>
}

export interface FidelityBreakdown {
  word: ModelScoreMap
  powerpoint: ModelScoreMap
  excel: ModelScoreMap
  all_apps: ModelScoreMap
}

export interface FileFidelitySection {
  overall: FidelityBreakdown
  by_feature: Record<string, Record<string, ModelScoreMap>>
}

export interface SizeBreakdown {
  small: ModelScoreMap
  medium: ModelScoreMap
  long: ModelScoreMap
}

export interface ComprehensionBySizeSection {
  word: SizeBreakdown
  powerpoint: SizeBreakdown
  excel: SizeBreakdown
}

export interface BenchmarkMetadata {
  benchmark_name: string
  version: string
  last_updated: string
  models: ModelInfo[]
}

export interface OCBLeaderboardData {
  metadata: BenchmarkMetadata
  overall: FileTypeBreakdown
  domain_qna: DomainQnASection
  file_fidelity: FileFidelitySection
  comprehension_by_size: ComprehensionBySizeSection
}

// UI helpers
export type TabId = 'overall' | 'domain-qna' | 'file-fidelity' | 'by-size'
export type FileTypeKey = 'word' | 'powerpoint' | 'excel' | 'multifile' | 'all_apps'
export type SizeKey = 'small' | 'medium' | 'long'

export interface ModelTableRow {
  modelId: string
  displayName: string
  org: string
  allApps?: number
  word?: number
  powerpoint?: number
  excel?: number
  multifile?: number
}
