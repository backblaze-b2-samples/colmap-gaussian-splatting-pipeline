"use client";

import { Boxes, HardDrive, Images, Sparkles } from "lucide-react";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Skeleton } from "@/components/ui/skeleton";
import { ErrorState } from "@/components/ui/error-state";
import { LoadingNotice } from "@/components/common/loading-notice";
import { useCaptureStats } from "@/lib/queries";

export function StatsCards() {
  const { data: stats, isLoading, error, refetch } = useCaptureStats();

  // Surface fetch failures inline rather than rendering zeros — that would lie
  // about the bucket state when really the API is just unreachable.
  if (error) {
    return (
      <Card>
        <CardContent className="p-0">
          <ErrorState error={error} onRetry={() => refetch()} />
        </CardContent>
      </Card>
    );
  }

  const cards = [
    { title: "Captures", value: stats?.total_captures ?? 0, icon: Boxes },
    { title: "Frames ingested", value: stats?.images_ingested ?? 0, icon: Images },
    {
      title: "Sparse points reconstructed",
      value: (stats?.sparse_points ?? 0).toLocaleString(),
      icon: Sparkles,
    },
    { title: "Artifacts on B2", value: stats?.artifact_bytes_human ?? "0 B", icon: HardDrive },
  ];

  return (
    <>
      {/* Stats scan the captures/ prefix, which can take a moment on a large
          bucket. State that in words rather than showing blank cards. */}
      {isLoading && <LoadingNotice className="mb-3" subject="capture metrics" />}
      <div className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
        {cards.map((card, i) => (
          <Card
            key={card.title}
            className={`card-hover animate-fade-in-up stagger-${i + 1}`}
          >
            <CardHeader className="flex flex-row items-center justify-between pt-4 pb-2 px-4 space-y-0">
              <CardTitle className="text-xs font-semibold text-muted-foreground">
                {card.title}
              </CardTitle>
              <div className="stat-icon-wrap">
                <card.icon className="h-4 w-4" />
              </div>
            </CardHeader>
            <CardContent className="pb-5 px-4">
              {isLoading ? (
                <Skeleton className="h-8 w-24" />
              ) : (
                <div className="stat-value">{card.value}</div>
              )}
            </CardContent>
          </Card>
        ))}
      </div>
    </>
  );
}
