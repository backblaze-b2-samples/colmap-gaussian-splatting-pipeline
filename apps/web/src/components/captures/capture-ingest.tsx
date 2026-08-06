"use client";

import { useRef, useState } from "react";
import { toast } from "sonner";
import { ImagePlus, Loader2, Video } from "lucide-react";

import { Button } from "@/components/ui/button";
import { useIngestImages, useIngestVideo } from "@/lib/queries";
import type { Capture } from "@colmap-gaussian-splatting-pipeline/shared";

/**
 * Frame ingest panel for a capture: uploads an image set or a capture video
 * into the capture's own inputs/ prefix on B2. A video is sampled into frames
 * server-side (bundled ffmpeg). Which control shows is driven by the capture's
 * source_type, set on the create form.
 */
export function CaptureIngest({ capture }: { capture: Capture }) {
  const isVideo = capture.source_type === "video";
  const inputRef = useRef<HTMLInputElement>(null);
  const [selected, setSelected] = useState<File[]>([]);
  const ingestImages = useIngestImages(capture.id);
  const ingestVideo = useIngestVideo(capture.id);
  const busy = ingestImages.isPending || ingestVideo.isPending;

  const onSubmit = async () => {
    if (selected.length === 0) return;
    try {
      if (isVideo) {
        await ingestVideo.mutateAsync(selected[0]);
        toast.success("Video ingested", { description: "Frames sampled and stored on B2." });
      } else {
        await ingestImages.mutateAsync(selected);
        toast.success(`${selected.length} frame(s) ingested`);
      }
      setSelected([]);
      if (inputRef.current) inputRef.current.value = "";
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Ingest failed");
    }
  };

  return (
    <div className="rounded-md border border-dashed border-border p-5">
      <div className="flex items-center gap-2 text-sm font-medium">
        {isVideo ? <Video className="h-4 w-4" /> : <ImagePlus className="h-4 w-4" />}
        {isVideo ? "Add a capture video" : "Add image frames"}
      </div>
      <p className="mt-1 text-xs text-muted-foreground">
        {isVideo
          ? "Upload one video; the server samples evenly-spread frames into captures/" +
            capture.id +
            "/inputs/."
          : "Upload overlapping photos. They are downscaled to " +
            capture.max_image_dimension +
            "px and stored under inputs/."}
      </p>
      <div className="mt-3 flex flex-wrap items-center gap-2">
        <input
          ref={inputRef}
          type="file"
          accept={isVideo ? "video/*" : "image/*"}
          multiple={!isVideo}
          onChange={(e) => setSelected(Array.from(e.target.files ?? []))}
          className="block max-w-full text-sm file:mr-3 file:rounded-md file:border file:border-border file:bg-muted file:px-3 file:py-1.5 file:text-sm file:font-medium hover:file:bg-muted/70"
        />
        <Button size="sm" onClick={onSubmit} disabled={busy || selected.length === 0}>
          {busy && <Loader2 className="h-3.5 w-3.5 animate-spin" aria-hidden />}
          {busy ? "Uploading…" : isVideo ? "Ingest video" : `Ingest ${selected.length || ""} frame(s)`}
        </Button>
      </div>
    </div>
  );
}
