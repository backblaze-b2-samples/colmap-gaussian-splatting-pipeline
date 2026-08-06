"use client";

import { useState } from "react";
import Image from "next/image";
import { Boxes, Loader2 } from "lucide-react";

import { Skeleton } from "@/components/ui/skeleton";
import { usePreviewUrl } from "@/lib/queries";
import type { CaptureStatus } from "@colmap-gaussian-splatting-pipeline/shared";

function PlaceholderTile({ label }: { label: string }) {
  return (
    <div className="flex h-full w-full flex-col items-center justify-center gap-2 bg-muted text-muted-foreground">
      <Boxes className="h-6 w-6" aria-hidden />
      <span className="text-xs">{label}</span>
    </div>
  );
}

/**
 * In-progress state for a running capture. The backend runs COLMAP in a
 * subprocess and streams NO per-stage progress, so this is deliberately
 * INDETERMINATE (a spinner + pulsing bar, never a fabricated percentage). It
 * lists the SfM stages so the main content shows real work is underway.
 */
function ProcessingTile() {
  const stages = [
    "SIFT feature extraction (CPU)",
    "Feature matching",
    "Incremental mapping (sparse SfM)",
    "Stage Nerfstudio/gsplat bundle",
    "Render point-cloud preview",
  ];
  return (
    <div
      role="status"
      className="flex h-full w-full flex-col items-center justify-center gap-3 bg-muted p-4 text-muted-foreground"
    >
      <div className="flex items-center gap-2 text-foreground">
        <Loader2 className="h-5 w-5 animate-spin text-primary" aria-hidden />
        <span className="text-sm font-medium">Reconstructing…</span>
      </div>
      <div className="h-1 w-40 overflow-hidden rounded-full bg-border">
        <div className="h-full w-full animate-pulse bg-primary/60" />
      </div>
      <ol className="space-y-1 text-xs">
        {stages.map((stage) => (
          <li key={stage} className="flex items-center gap-2">
            <span className="h-1.5 w-1.5 shrink-0 rounded-full bg-muted-foreground/50" aria-hidden />
            {stage}
          </li>
        ))}
      </ol>
    </div>
  );
}

/**
 * Sparse point-cloud preview PNG, served from B2 via a short-lived presigned
 * URL. The PNG is rendered by the pipeline (matplotlib) and stored at
 * captures/<id>/previews/preview.png — proof of the "rendered previews from B2"
 * feature.
 */
export function CapturePreview({
  previewKey,
  alt,
  sizes = "(max-width: 768px) 100vw, 320px",
  status,
}: {
  previewKey: string | null;
  alt: string;
  sizes?: string;
  status?: CaptureStatus;
}) {
  const { data, isLoading, isError } = usePreviewUrl(
    previewKey ?? undefined,
    !!previewKey
  );
  const [imgState, setImgState] = useState<"loading" | "ready" | "error">("loading");

  if (status === "running") return <ProcessingTile />;
  if (!previewKey) return <PlaceholderTile label="No preview yet" />;
  if (isLoading || !data) return <Skeleton className="h-full w-full" />;
  if (isError || imgState === "error")
    return <PlaceholderTile label="Preview unavailable" />;

  return (
    <div key={data.url} className="relative h-full w-full">
      <Image
        src={data.url}
        alt={alt}
        fill
        sizes={sizes}
        unoptimized
        loading="eager"
        className={`object-contain ${imgState === "ready" ? "" : "opacity-0"}`}
        onLoad={() => setImgState("ready")}
        onError={() => setImgState("error")}
      />
      {imgState === "loading" && <Skeleton className="absolute inset-0" />}
    </div>
  );
}
