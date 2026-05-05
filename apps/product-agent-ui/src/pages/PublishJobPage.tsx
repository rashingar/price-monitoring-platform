import { apiClient } from "../api/client";
import { ModelJobForm } from "../components/forms/ModelJobForm";
import { useCreateJob } from "../hooks/useCreateJob";
import { usePersistentPageState } from "../hooks/usePersistentPageState";

export function PublishJobPage() {
  const { error, isSubmitting, submitJob } = useCreateJob(apiClient.createPublishJob);
  const [model, setModel, resetModel] = usePersistentPageState(
    "product-agent-ui:publish:v1",
    "",
  );

  return (
    <div className="page-stack narrow">
      <section className="page-header">
        <p className="eyebrow">Publish</p>
        <h2>Start publish job</h2>
        <button className="text-button" type="button" onClick={resetModel}>
          Reset saved Publish state
        </button>
      </section>
      <section className="panel">
        <ModelJobForm
          actionLabel="Start publish job"
          busyLabel="Starting publish job..."
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
