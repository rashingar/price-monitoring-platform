import { apiClient } from "../api/client";
import {
  initialPrepareFormState,
  PrepareJobForm,
  type PrepareFormState,
} from "../components/forms/PrepareJobForm";
import { useState } from "react";
import { useCreateJob } from "../hooks/useCreateJob";
import { usePersistentPageState } from "../hooks/usePersistentPageState";

export function PrepareJobPage() {
  const { error, isSubmitting, submitJob } = useCreateJob(apiClient.createPrepareJob);
  const [form, setForm, resetForm] = usePersistentPageState<PrepareFormState>(
    "product-agent-ui:prepare:v1",
    initialPrepareFormState,
  );
  const [resetSeq, setResetSeq] = useState(0);
  const handleReset = () => {
    resetForm();
    setResetSeq((value) => value + 1);
  };

  return (
    <div className="page-stack narrow">
      <section className="page-header">
        <p className="eyebrow">Prepare</p>
        <h2>Start prepare job</h2>
        <button className="text-button" type="button" onClick={handleReset}>
          Reset saved Prepare state
        </button>
      </section>
      <section className="panel">
        <PrepareJobForm
          key={resetSeq}
          error={error}
          isSubmitting={isSubmitting}
          onSubmit={submitJob}
          initialForm={form}
          onFormChange={setForm}
        />
      </section>
    </div>
  );
}
