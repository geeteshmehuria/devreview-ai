"use client";

import { useQuery } from "@tanstack/react-query";
import { useParams, useRouter } from "next/navigation";
import { ArrowLeft, Loader2 } from "lucide-react";
import { reviewsApi } from "@/lib/api/reviews";
import { ReviewResultPanel } from "@/components/review/review-result-panel";

export default function ReviewDetailPage() {
  const { id } = useParams<{ id: string }>();
  const router = useRouter();

  const { data: review, isLoading, error } = useQuery({
    queryKey: ["review", id],
    queryFn: () => reviewsApi.get(id),
    enabled: !!id,
  });

  if (isLoading) {
    return (
      <div className="flex items-center justify-center h-64">
        <Loader2 className="w-8 h-8 text-brand-400 animate-spin" />
      </div>
    );
  }

  if (error || !review) {
    return (
      <div className="text-center py-16">
        <p className="text-slate-400">Review not found.</p>
      </div>
    );
  }

  return (
    <div className="max-w-5xl space-y-4">
      <button
        onClick={() => router.back()}
        className="flex items-center gap-2 text-sm text-slate-400 hover:text-white transition-colors"
      >
        <ArrowLeft className="w-4 h-4" />
        Back to History
      </button>
      <ReviewResultPanel review={review} />
    </div>
  );
}
