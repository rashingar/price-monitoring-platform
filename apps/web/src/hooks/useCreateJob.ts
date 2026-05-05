import { useEffect, useRef, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getApiErrorMessage } from "../api/client";
import { getJobIdentifier } from "../api/jobUtils";
import type { Job } from "../api/types";
import { useGlobalJobs } from "./useGlobalJobs";

export function useCreateJob<TRequest>(createJob: (request: TRequest) => Promise<Job>) {
  const navigate = useNavigate();
  const { trackJob } = useGlobalJobs();
  const isMountedRef = useRef(true);
  const [isSubmitting, setIsSubmitting] = useState(false);
  const [error, setError] = useState<string | null>(null);

  useEffect(() => {
    return () => {
      isMountedRef.current = false;
    };
  }, []);

  async function submitJob(request: TRequest) {
    setIsSubmitting(true);
    setError(null);

    try {
      const job = await createJob(request);
      trackJob(job);
      const jobId = getJobIdentifier(job);
      if (!jobId) {
        throw new Error("The backend response did not include job_id or id.");
      }

      if (isMountedRef.current) {
        navigate(`/jobs/${encodeURIComponent(jobId)}`);
      }
    } catch (submitError) {
      if (isMountedRef.current) {
        setError(getApiErrorMessage(submitError));
      }
    } finally {
      if (isMountedRef.current) {
        setIsSubmitting(false);
      }
    }
  }

  return {
    isSubmitting,
    error,
    submitJob,
  };
}
