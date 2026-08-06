"use client";

import Link from "next/link";
import { Plus, Boxes } from "lucide-react";

import { Button } from "@/components/ui/button";
import { Card, CardContent } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { EmptyState } from "@/components/ui/empty-state";
import { ErrorState } from "@/components/ui/error-state";
import { useCaptures } from "@/lib/queries";
import { CapturePreview } from "./capture-preview";
import { CaptureStatusBadge } from "./capture-status-badge";

export function CapturesList() {
  const { data: captures = [], isLoading, error, refetch } = useCaptures();

  if (error) {
    return (
      <Card>
        <CardContent className="p-0">
          <ErrorState error={error} onRetry={() => refetch()} />
        </CardContent>
      </Card>
    );
  }

  if (isLoading) {
    return (
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
        {Array.from({ length: 3 }).map((_, i) => (
          <Skeleton key={i} className="h-64 w-full rounded-md" />
        ))}
      </div>
    );
  }

  if (captures.length === 0) {
    return (
      <Card>
        <CardContent className="p-0">
          <EmptyState
            icon={Boxes}
            title="No captures yet"
            description="Create a capture, add an image set or a capture video, and run COLMAP structure-from-motion — every artifact is versioned on B2."
            action={
              <Button asChild size="sm">
                <Link href="/captures/new">
                  <Plus className="h-3.5 w-3.5" />
                  New capture
                </Link>
              </Button>
            }
          />
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
      {captures.map((capture) => (
        <Link key={capture.id} href={`/captures/${capture.id}`} className="group">
          <Card className="card-hover overflow-hidden">
            <div className="relative aspect-video bg-muted">
              <CapturePreview
                previewKey={capture.preview_key}
                alt={`Preview of ${capture.name}`}
                status={capture.status}
              />
            </div>
            <CardContent className="space-y-2 p-4">
              <div className="flex items-start justify-between gap-2">
                <p className="min-w-0 truncate font-semibold group-hover:text-primary">
                  {capture.name}
                </p>
                <CaptureStatusBadge status={capture.status} />
              </div>
              <p className="text-xs text-muted-foreground">
                {capture.input_count} frame{capture.input_count === 1 ? "" : "s"} ·{" "}
                {capture.source_type === "video" ? "video" : "image set"} ·{" "}
                {capture.quality}
              </p>
              {capture.status === "done" && (
                <p className="text-xs text-muted-foreground">
                  {capture.metrics.registered_images} registered ·{" "}
                  {capture.metrics.sparse_points.toLocaleString()} points
                </p>
              )}
              {capture.status === "failed" && capture.error && (
                <p className="truncate text-xs text-destructive">{capture.error}</p>
              )}
            </CardContent>
          </Card>
        </Link>
      ))}
    </div>
  );
}
