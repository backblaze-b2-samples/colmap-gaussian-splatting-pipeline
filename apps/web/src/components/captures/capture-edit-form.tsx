"use client";

import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { useCapture } from "@/lib/queries";
import { CaptureForm } from "./capture-form";

/** Loads a capture by id and hands it to CaptureForm pre-filled for editing. */
export function CaptureEditForm({ id }: { id: string }) {
  const { data: capture, isLoading, error, refetch } = useCapture(id);

  if (error) return <ErrorState error={error} onRetry={() => refetch()} />;
  if (isLoading || !capture) return <Skeleton className="h-96 w-full rounded-md" />;

  return <CaptureForm capture={capture} />;
}
