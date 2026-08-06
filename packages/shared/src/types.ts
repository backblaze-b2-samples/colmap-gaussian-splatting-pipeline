export type FileStatus = "uploading" | "complete" | "error";

export interface FileMetadata {
  key: string;
  filename: string;
  folder: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
}

export interface FileMetadataDetail {
  filename: string;
  size_bytes: number;
  size_human: string;
  mime_type: string;
  extension: string;
  md5: string;
  sha256: string;
  uploaded_at: string;
  /** Set when a format-specific extractor was skipped or failed (e.g. an image
   *  above the decompression-bomb decode limit). Core fields stay exact. */
  metadata_warning: string | null;
  // Image-specific
  image_width: number | null;
  image_height: number | null;
  exif: Record<string, string> | null;
  // PDF-specific
  pdf_pages: number | null;
  pdf_author: string | null;
  pdf_title: string | null;
  // Audio/Video
  duration_seconds: number | null;
  codec: string | null;
  bitrate: number | null;
}

export interface FileUploadResponse {
  key: string;
  filename: string;
  size_bytes: number;
  size_human: string;
  content_type: string;
  uploaded_at: string;
  url: string | null;
  metadata: FileMetadataDetail | null;
}

export interface DailyUploadCount {
  date: string;
  uploads: number;
}

export interface UploadStats {
  total_files: number;
  total_size_bytes: number;
  total_size_human: string;
  uploads_today: number;
  total_downloads: number;
}

// --- Photogrammetry captures (primary entity) ------------------------------

export type SourceType = "images" | "video";
export type Quality = "low" | "medium" | "high";
export type Matcher = "exhaustive" | "sequential";
export type CaptureStatus = "draft" | "ready" | "running" | "done" | "failed";
export type StageStatus = "pending" | "running" | "done" | "skipped" | "failed";

export interface CaptureStage {
  key: string;
  label: string;
  status: StageStatus;
  detail: string | null;
}

export interface CaptureArtifact {
  name: string;
  kind: string;
  key: string;
  size_bytes: number;
  size_human: string;
  version_id: string | null;
}

export interface CaptureMetrics {
  input_images: number;
  registered_images: number;
  sparse_points: number;
  observations: number;
  mean_reprojection_error: number;
  dense_enabled: boolean;
  device: string;
  source_bytes: number;
  artifact_bytes: number;
  duration_seconds: number;
}

export interface Capture {
  id: string;
  name: string;
  source_type: SourceType;
  quality: Quality;
  matcher: Matcher;
  max_image_dimension: number;
  status: CaptureStatus;
  created_at: string;
  updated_at: string;
  input_count: number;
  error: string | null;
  metrics: CaptureMetrics;
  stages: CaptureStage[];
  artifacts: CaptureArtifact[];
  preview_key: string | null;
  train_command: string | null;
}

/** POST /captures body. */
export interface CaptureCreate {
  name: string;
  source_type: SourceType;
  quality: Quality;
  matcher: Matcher;
  max_image_dimension: number;
}

/** PATCH /captures/{id} body — every field optional. */
export type CaptureUpdate = Partial<CaptureCreate>;

export interface CaptureStats {
  total_captures: number;
  draft: number;
  ready: number;
  running: number;
  done: number;
  failed: number;
  images_ingested: number;
  sparse_points: number;
  artifact_count: number;
  artifact_bytes: number;
  artifact_bytes_human: string;
  source_bytes: number;
  source_bytes_human: string;
}
