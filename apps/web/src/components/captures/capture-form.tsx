"use client";

import { useRouter } from "next/navigation";
import { useForm } from "react-hook-form";
import { zodResolver } from "@hookform/resolvers/zod";
import { z } from "zod";
import { toast } from "sonner";

import { Button } from "@/components/ui/button";
import { Card, CardContent, CardHeader, CardTitle } from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { RadioGroup, RadioGroupItem } from "@/components/ui/radio-group";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Form,
  FormControl,
  FormDescription,
  FormField,
  FormItem,
  FormLabel,
  FormMessage,
} from "@/components/ui/form";
import { useCreateCapture, useUpdateCapture } from "@/lib/queries";
import type { Capture } from "@colmap-gaussian-splatting-pipeline/shared";

const schema = z.object({
  name: z.string().min(1, "Give the capture a name").max(120),
  source_type: z.enum(["images", "video"]),
  quality: z.enum(["low", "medium", "high"]),
  matcher: z.enum(["exhaustive", "sequential"]),
  // Kept a string field (parsed on submit) so the input never fights
  // react-hook-form over number coercion.
  max_image_dimension: z
    .string()
    .regex(/^\d+$/, "Enter a whole number")
    .refine((v) => {
      const n = Number(v);
      return n >= 256 && n <= 8192;
    }, "Between 256 and 8192"),
});

type CaptureFormValues = z.infer<typeof schema>;

function toDefaults(capture?: Capture): CaptureFormValues {
  return {
    name: capture?.name ?? "",
    source_type: capture?.source_type ?? "images",
    quality: capture?.quality ?? "medium",
    matcher: capture?.matcher ?? "exhaustive",
    max_image_dimension: String(capture?.max_image_dimension ?? 1600),
  };
}

export function CaptureForm({ capture }: { capture?: Capture }) {
  const isEdit = Boolean(capture);
  const router = useRouter();
  const createCapture = useCreateCapture();
  const updateCapture = useUpdateCapture(capture?.id ?? "");

  const form = useForm<CaptureFormValues>({
    resolver: zodResolver(schema),
    defaultValues: toDefaults(capture),
  });

  const onSubmit = async (values: CaptureFormValues) => {
    const payload = {
      name: values.name,
      source_type: values.source_type,
      quality: values.quality,
      matcher: values.matcher,
      max_image_dimension: Number(values.max_image_dimension),
    };
    try {
      if (isEdit && capture) {
        await updateCapture.mutateAsync(payload);
        toast.success("Capture updated");
        router.push(`/captures/${capture.id}`);
      } else {
        const created = await createCapture.mutateAsync(payload);
        toast.success("Capture created", {
          description: "Add frames on the next page, then press Run.",
        });
        router.push(`/captures/${created.id}`);
      }
    } catch (err) {
      toast.error(err instanceof Error ? err.message : "Could not save the capture");
    }
  };

  const submitting = createCapture.isPending || updateCapture.isPending;

  return (
    <Form {...form}>
      <form onSubmit={form.handleSubmit(onSubmit)} className="space-y-6">
        <Card>
          <CardHeader className="border-b border-border py-4 px-5">
            <CardTitle className="card-title">
              {isEdit ? "Edit capture" : "New capture"}
            </CardTitle>
          </CardHeader>
          <CardContent className="p-5 space-y-6">
            <FormField
              control={form.control}
              name="name"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Name</FormLabel>
                  <FormControl>
                    <Input
                      placeholder={isEdit ? undefined : "e.g. heritage-facade-01"}
                      {...field}
                    />
                  </FormControl>
                  {!isEdit && (
                    <FormDescription>
                      A short, human name for this reconstruction.
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="source_type"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Source</FormLabel>
                  <FormControl>
                    <RadioGroup
                      value={field.value}
                      onValueChange={field.onChange}
                      className="grid gap-2 sm:grid-cols-2"
                    >
                      <RadioOption
                        value="images"
                        label="Image set"
                        hint="Upload overlapping photos"
                        selected={field.value === "images"}
                      />
                      <RadioOption
                        value="video"
                        label="Capture video"
                        hint="Server samples frames"
                        selected={field.value === "video"}
                      />
                    </RadioGroup>
                  </FormControl>
                  {!isEdit && (
                    <FormDescription>
                      Default: Image set. A video is sampled into frames on ingest.
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="quality"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Quality (SfM preset)</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger className="w-60">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="low">Low (fast)</SelectItem>
                      <SelectItem value="medium">Medium</SelectItem>
                      <SelectItem value="high">High</SelectItem>
                    </SelectContent>
                  </Select>
                  {!isEdit && (
                    <FormDescription>
                      Default: Medium — more features per image at higher presets.
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="matcher"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Matcher</FormLabel>
                  <Select onValueChange={field.onChange} value={field.value}>
                    <FormControl>
                      <SelectTrigger className="w-72">
                        <SelectValue />
                      </SelectTrigger>
                    </FormControl>
                    <SelectContent>
                      <SelectItem value="exhaustive">Exhaustive (small sets)</SelectItem>
                      <SelectItem value="sequential">Sequential (video/ordered)</SelectItem>
                    </SelectContent>
                  </Select>
                  {!isEdit && (
                    <FormDescription>
                      Default: Exhaustive. Use Sequential for ordered video frames.
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />

            <FormField
              control={form.control}
              name="max_image_dimension"
              render={({ field }) => (
                <FormItem>
                  <FormLabel>Max image dimension</FormLabel>
                  <FormControl>
                    <Input
                      type="number"
                      step="1"
                      min="256"
                      max="8192"
                      className="w-40 font-mono tabular-nums"
                      {...field}
                    />
                  </FormControl>
                  {!isEdit && (
                    <FormDescription>
                      Default: 1600 — downscales large frames so CPU SfM finishes
                      quickly.
                    </FormDescription>
                  )}
                  <FormMessage />
                </FormItem>
              )}
            />
          </CardContent>
        </Card>

        <div className="flex items-center justify-end gap-2">
          <Button type="button" variant="outline" onClick={() => router.back()}>
            Cancel
          </Button>
          <Button type="submit" disabled={submitting}>
            {submitting ? "Saving..." : isEdit ? "Save changes" : "Create capture"}
          </Button>
        </div>
      </form>
    </Form>
  );
}

function RadioOption({
  value,
  label,
  hint,
  selected,
}: {
  value: string;
  label: string;
  hint: string;
  selected: boolean;
}) {
  return (
    <label
      className={`flex cursor-pointer items-start gap-3 rounded-md border p-3 transition-colors ${
        selected ? "border-primary bg-primary/5" : "border-border hover:bg-muted/60"
      }`}
    >
      <RadioGroupItem value={value} className="mt-0.5" />
      <span className="min-w-0">
        <span className="block text-sm font-medium">{label}</span>
        <span className="block text-xs text-muted-foreground">{hint}</span>
      </span>
    </label>
  );
}
