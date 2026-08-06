"use client";

import { useEffect, useState } from "react";
import Link from "next/link";
import { useRouter } from "next/navigation";
import { toast } from "sonner";
import {
  Check,
  Download,
  Loader2,
  Minus,
  Pencil,
  Play,
  RotateCw,
  Trash2,
  X,
} from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { ConfirmDialog } from "@/components/common/confirm-dialog";
import { getDownloadUrl } from "@/lib/api-client";
import { startBrowserDownload } from "@/lib/browser-download";
import { useCapture, useDeleteCapture, useRunCapture } from "@/lib/queries";
import type {
  Capture,
  CaptureArtifact,
  CaptureStage,
} from "@colmap-gaussian-splatting-pipeline/shared";
import { CaptureIngest } from "./capture-ingest";
import { CapturePreview } from "./capture-preview";
import { CaptureStatusBadge } from "./capture-status-badge";

async function downloadArtifact(artifact: CaptureArtifact) {
  try {
    const { url } = await getDownloadUrl(artifact.key);
    const filename = artifact.key.split("/").pop() ?? artifact.name;
    startBrowserDownload(url, filename);
  } catch (err) {
    toast.error(err instanceof Error ? err.message : "Download failed");
  }
}

export function CaptureDetail({ id }: { id: string }) {
  const router = useRouter();
  const { data: capture, isLoading, error, refetch } = useCapture(id);
  const runCapture = useRunCapture();
  const deleteCapture = useDeleteCapture();

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !capture) return <Skeleton className="h-96 w-full rounded-md" />;

  const busy = capture.status === "running" || runCapture.isPending;
  const canRun = capture.input_count > 0 && !busy;
  const ran = capture.status === "done" || capture.status === "failed";

  const onRun = async () => {
    try {
      await runCapture.mutateAsync(capture.id);
      toast.success("Reconstruction started");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not start the run");
    }
  };

  const onDelete = async () => {
    try {
      await deleteCapture.mutateAsync(capture.id);
      toast.success("Capture deleted");
      router.push("/captures");
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Delete failed");
    }
  };

  return (
    <div className="space-y-6">
      <div className="flex flex-wrap items-start justify-between gap-3 border-b border-border pb-5">
        <div className="min-w-0">
          <div className="flex items-center gap-3">
            <h1 className="page-title truncate">{capture.name}</h1>
            <CaptureStatusBadge status={capture.status} />
          </div>
          <p className="mt-1.5 text-sm text-muted-foreground">
            {capture.input_count} frame{capture.input_count === 1 ? "" : "s"} ·{" "}
            {capture.source_type === "video" ? "capture video" : "image set"} ·
            updated {new Date(capture.updated_at).toLocaleString()}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <Button onClick={onRun} disabled={!canRun} size="sm" title={capture.input_count === 0 ? "Add frames first" : undefined}>
            {ran ? <RotateCw className="h-3.5 w-3.5" /> : <Play className="h-3.5 w-3.5" />}
            {ran ? "Re-run" : "Run"}
          </Button>
          <Button asChild size="sm" variant="outline" disabled={busy}>
            <Link href={`/captures/${capture.id}/edit`}>
              <Pencil className="h-3.5 w-3.5" />
              Edit
            </Link>
          </Button>
          <ConfirmDialog
            title="Delete this capture?"
            description="This removes the manifest and every artifact (frames, sparse model, bundle, preview) under this capture's B2 prefix. This cannot be undone."
            onConfirm={onDelete}
            trigger={
              <Button size="sm" variant="outline" className="text-destructive">
                <Trash2 className="h-3.5 w-3.5" />
                Delete
              </Button>
            }
          />
        </div>
      </div>

      {capture.status === "failed" && capture.error && (
        <Alert variant="destructive">
          <AlertTitle>Reconstruction failed</AlertTitle>
          <AlertDescription>{capture.error}</AlertDescription>
        </Alert>
      )}

      {capture.status !== "running" && capture.status !== "done" && (
        <CaptureIngest capture={capture} />
      )}

      <div className="grid gap-6 lg:grid-cols-2">
        <Card className="overflow-hidden">
          <div className="relative aspect-video bg-muted">
            <CapturePreview
              previewKey={capture.preview_key}
              alt={`Sparse point-cloud preview of ${capture.name}`}
              sizes="(max-width: 1024px) 100vw, 600px"
              status={capture.status}
            />
          </div>
        </Card>

        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">Configuration</CardTitle>
          </CardHeader>
          <CardContent className="p-5">
            <ConfigRow label="Source" value={capture.source_type === "video" ? "Capture video" : "Image set"} />
            <ConfigRow label="Quality" value={capture.quality} />
            <ConfigRow label="Matcher" value={capture.matcher} />
            <ConfigRow label="Max image dimension" value={`${capture.max_image_dimension}px`} />
            <ConfigRow label="Frames ingested" value={String(capture.input_count)} />
            {capture.status === "done" && (
              <ConfigRow label="Device" value={capture.metrics.device.toUpperCase()} />
            )}
          </CardContent>
        </Card>
      </div>

      {capture.stages.length > 0 && (
        <StageTimeline
          stages={capture.stages}
          running={capture.status === "running"}
          startedAt={capture.started_at}
        />
      )}

      {capture.status === "done" && (
        <>
          <MetricsCard capture={capture} />
          {capture.train_command && <TrainCommandCard command={capture.train_command} enabled={capture.metrics.dense_enabled} />}
          <ArtifactsCard capture={capture} />
        </>
      )}
    </div>
  );
}

function ConfigRow({ label, value }: { label: string; value: string }) {
  return (
    <div className="flex items-center justify-between border-b border-border py-2 last:border-0">
      <span className="text-sm text-muted-foreground">{label}</span>
      <span className="text-sm font-medium capitalize">{value}</span>
    </div>
  );
}

const STAGE_ICON = {
  done: <Check className="h-3.5 w-3.5 text-[var(--brand-b2)]" aria-hidden />,
  skipped: <Minus className="h-3.5 w-3.5 text-muted-foreground" aria-hidden />,
  failed: <X className="h-3.5 w-3.5 text-destructive" aria-hidden />,
  running: <span className="h-1.5 w-1.5 rounded-full bg-primary" aria-hidden />,
  pending: <span className="h-1.5 w-1.5 rounded-full bg-muted-foreground/40" aria-hidden />,
} as const;

const STAGE_TERMINAL: readonly CaptureStage["status"][] = ["done", "skipped", "failed"];

function StageTimeline({
  stages,
  running = false,
  startedAt = null,
}: {
  stages: CaptureStage[];
  running?: boolean;
  startedAt?: string | null;
}) {
  const total = stages.length;
  const completed = stages.filter((s) => STAGE_TERMINAL.includes(s.status)).length;
  const pct = total > 0 ? Math.round((completed / total) * 100) : 0;
  // While running, the active stage is the first one not yet terminal. The
  // backend streams a snapshot after each transition, so this advances live.
  const activeKey = running
    ? stages.find((s) => !STAGE_TERMINAL.includes(s.status))?.key ?? null
    : null;

  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Pipeline stages</CardTitle>
      </CardHeader>
      <CardContent className="p-5">
        {running && (
          <div className="mb-5 space-y-2">
            <div className="flex items-center justify-between text-xs text-muted-foreground">
              <span className="tabular-nums">
                {completed} of {total} stages complete
              </span>
              <RunTimer startedAt={startedAt} />
            </div>
            <div
              className="h-1.5 w-full overflow-hidden rounded-full bg-border"
              role="progressbar"
              aria-valuenow={pct}
              aria-valuemin={0}
              aria-valuemax={100}
            >
              <div
                className="h-full rounded-full bg-primary transition-all duration-500"
                style={{ width: `${pct}%` }}
              />
            </div>
          </div>
        )}
        <ol className="space-y-2.5">
          {stages.map((stage) => {
            const isActive = stage.key === activeKey;
            return (
              <li
                key={stage.key}
                className={`flex items-center gap-3 ${isActive ? "text-foreground" : ""}`}
              >
                <span className="flex h-5 w-5 items-center justify-center">
                  {isActive ? (
                    <Loader2 className="h-3.5 w-3.5 animate-spin text-primary" aria-hidden />
                  ) : (
                    STAGE_ICON[stage.status]
                  )}
                </span>
                <span className="text-sm font-medium">{stage.label}</span>
                {(isActive || stage.detail) && (
                  <span className="ml-auto truncate text-xs text-muted-foreground">
                    {isActive ? "Working…" : stage.detail}
                  </span>
                )}
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}

/**
 * Live elapsed-time counter, ticking each second while a run is active. Anchors
 * to the capture's authoritative server run-start timestamp (`started_at`, UTC
 * ISO) so the elapsed value reflects true time-since-run-start and survives a
 * page reload. Falls back to mount time only for older captures with no
 * `started_at`. `Date.parse` yields UTC epoch ms regardless of the offset
 * suffix, so the subtraction against `Date.now()` is timezone-safe.
 */
function RunTimer({ startedAt }: { startedAt: string | null }) {
  const parsed = startedAt ? Date.parse(startedAt) : NaN;
  const anchor = Number.isNaN(parsed) ? null : parsed;
  const [seconds, setSeconds] = useState(() =>
    anchor === null ? 0 : Math.max(0, Math.floor((Date.now() - anchor) / 1000)),
  );
  useEffect(() => {
    const base = anchor ?? Date.now();
    const tick = () =>
      setSeconds(Math.max(0, Math.floor((Date.now() - base) / 1000)));
    tick();
    const id = setInterval(tick, 1000);
    return () => clearInterval(id);
  }, [anchor]);
  return <span className="tabular-nums">{formatDuration(seconds)} elapsed</span>;
}

/** Seconds -> compact human duration, e.g. 166 -> "2m 46s", 42 -> "42s". */
function formatDuration(totalSeconds: number): string {
  const s = Math.max(0, Math.round(totalSeconds));
  if (s < 60) return `${s}s`;
  return `${Math.floor(s / 60)}m ${s % 60}s`;
}

function MetricsCard({ capture }: { capture: Capture }) {
  const m = capture.metrics;
  const rows: [string, string][] = [
    ["Input images", m.input_images.toLocaleString()],
    ["Registered images", m.registered_images.toLocaleString()],
    ["Sparse points", m.sparse_points.toLocaleString()],
    ["Observations", m.observations.toLocaleString()],
    ["Mean reprojection error", `${m.mean_reprojection_error}px`],
    ["Dense MVS", m.dense_enabled ? "Ran (CUDA)" : "Skipped (CPU)"],
    ["Run time", formatDuration(m.duration_seconds)],
  ];
  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Reconstruction metrics</CardTitle>
      </CardHeader>
      <CardContent className="p-5">
        <div className="mb-4 rounded-md border border-border bg-muted/40 p-4">
          <p className="text-xs font-medium text-muted-foreground">Sparse point cloud</p>
          <p className="stat-value">{m.sparse_points.toLocaleString()}</p>
          <p className="text-xs text-muted-foreground">
            reconstructed from {m.registered_images} of {m.input_images} frames on{" "}
            {m.device.toUpperCase()} — {m.artifact_bytes.toLocaleString()} bytes of
            artifacts staged from {m.source_bytes.toLocaleString()} bytes of frames.
          </p>
        </div>
        <div className="grid gap-x-8 gap-y-2 sm:grid-cols-2">
          {rows.map(([label, value]) => (
            <div key={label} className="flex items-center justify-between border-b border-border py-1.5">
              <span className="text-sm text-muted-foreground">{label}</span>
              <span className="text-sm font-medium tabular-nums">{value}</span>
            </div>
          ))}
        </div>
      </CardContent>
    </Card>
  );
}

function TrainCommandCard({ command, enabled }: { command: string; enabled: boolean }) {
  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Gaussian Splatting / NeRF training</CardTitle>
      </CardHeader>
      <CardContent className="p-5 space-y-3">
        <p className="text-sm text-muted-foreground">
          {enabled
            ? "Dense MVS ran on this CUDA host. The staged bundle is ready to train:"
            : "The GPU-only training tail is staged, not run here (no CUDA device). Download the bundle to a GPU host and run:"}
        </p>
        <pre className="overflow-x-auto rounded-md border border-border bg-muted/40 p-3 font-mono text-xs">
          {command}
        </pre>
      </CardContent>
    </Card>
  );
}

function ArtifactsCard({ capture }: { capture: Capture }) {
  return (
    <Card>
      <CardHeader className="border-b border-border py-4 px-5">
        <CardTitle className="card-title">Artifacts on B2</CardTitle>
      </CardHeader>
      <CardContent className="p-5">
        <ul className="space-y-2">
          {capture.artifacts.map((artifact) => (
            <li
              key={artifact.key}
              className="flex items-center justify-between gap-3 rounded-md border border-border p-3"
            >
              <div className="min-w-0">
                <p className="truncate text-sm font-medium capitalize">
                  {artifact.name.replace(/_/g, " ")}
                </p>
                <p className="truncate font-mono text-xs text-muted-foreground">
                  {artifact.key} · {artifact.size_human}
                  {artifact.version_id && (
                    <> · v{artifact.version_id.slice(0, 8)}</>
                  )}
                </p>
              </div>
              <Button size="sm" variant="outline" onClick={() => downloadArtifact(artifact)}>
                <Download className="h-3.5 w-3.5" />
                Download
              </Button>
            </li>
          ))}
        </ul>
      </CardContent>
    </Card>
  );
}
