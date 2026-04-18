export interface WikiPage {
  id: string;
  slug: string;
  entityName: string;
  entityType: string;
  contentMarkdown: string;
  sourceBlocks: SourceBlock[];
  versionNumber: number;
  origin: string;
  createdAt: string;
  lastModified: string;
  conflictStatus: string | null;
  images?: WikiImage[];
  crossLinksFrom?: CrossLinkWithTarget[];
}

export interface SourceBlock {
  text: string;
  source_doc: string;
  heading_path: string[];
  paragraph_index: number;
  content_hash: string;
  section_type: string;
}

export interface WikiImage {
  id: string;
  filename: string;
  altText: string | null;
  caption: string | null;
  url: string;
  sourceDoc: string | null;
  isPrimary: boolean;
  origin: string;
  sortOrder: number;
}

export interface WikiVersion {
  id: string;
  versionNumber: number;
  origin: string;
  createdAt: string;
  changeSummary: string | null;
  contentMarkdown?: string;
}

export interface CrossLinkWithTarget {
  id: string;
  targetPage: {
    slug: string;
    entityName: string;
  };
}

export interface QAResponse {
  answer: string;
  sources: QASource[];
  indexStaleness: {
    isStale: boolean;
    lastBuilt: string | null;
    latestEdit: string | null;
  };
}

export interface QASource {
  type: string;
  metadata: Record<string, unknown>;
  similarity: number;
  excerpt: string;
}

export type EntityType =
  | "character"
  | "location"
  | "era"
  | "event"
  | "faction"
  | "artifact"
  | "concept"
  | "species"
  | "other";

export const ENTITY_TYPES: EntityType[] = [
  "character",
  "location",
  "era",
  "event",
  "faction",
  "artifact",
  "concept",
  "species",
  "other",
];

export const SECTION_TYPES = [
  "overview",
  "attributes",
  "relationships",
  "history",
  "appearances",
  "abilities",
  "culture",
  "geography",
  "timeline",
  "other",
] as const;
