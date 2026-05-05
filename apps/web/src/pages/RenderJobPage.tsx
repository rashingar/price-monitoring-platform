import { apiClient } from "../api/client";
import { ModelJobForm } from "../components/forms/ModelJobForm";
import { useCreateJob } from "../hooks/useCreateJob";
import { usePersistentPageState } from "../hooks/usePersistentPageState";

export function RenderJobPage() {
  const { error, isSubmitting, submitJob } = useCreateJob(apiClient.createRenderJob);
  const [model, setModel, resetModel] = usePersistentPageState(
    "product-agent-ui:render:v1",
    "",
  );

  return (
    <div className="page-stack narrow">
      <section className="page-header">
        <p className="eyebrow">Render</p>
        <h2>Start render job</h2>
        <button className="text-button" type="button" onClick={resetModel}>
          Reset saved Render state
        </button>
      </section>
      <section className="panel">
        <ModelJobForm
          actionLabel="Start render job"
          busyLabel="Starting render job..."
          error={error}
          isSubmitting={isSubmitting}
          onSubmit={submitJob}
          initialModel={model}
          onModelChange={setModel}
        />
      </section>
    </div>
  );
}
