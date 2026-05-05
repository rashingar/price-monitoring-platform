import { type FormEvent, useEffect, useState } from "react";
import type { ModelJobRequest } from "../../api/types";

interface ModelJobFormProps {
  actionLabel: string;
  busyLabel: string;
  error: string | null;
  isSubmitting: boolean;
  onSubmit: (request: ModelJobRequest) => void;
  initialModel?: string;
  onModelChange?: (model: string) => void;
}

export function ModelJobForm({
  actionLabel,
  busyLabel,
  error,
  isSubmitting,
  onSubmit,
  initialModel = "",
  onModelChange,
}: ModelJobFormProps) {
  const [model, setModel] = useState(initialModel);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    setModel(initialModel);
  }, [initialModel]);

  useEffect(() => {
    onModelChange?.(model);
  }, [model, onModelChange]);

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    const trimmedModel = model.trim();
    if (trimmedModel.length === 0) {
      setLocalError("Model is required.");
      return;
    }

    setLocalError(null);
    onSubmit({ model: trimmedModel });
  }

  return (
    <form className="form" onSubmit={handleSubmit}>
      {(localError ?? error) ? (
        <div className="form-error" role="alert">
          {localError ?? error}
        </div>
      ) : null}

      <label>
        <span>Model</span>
        <input
          required
          value={model}
          onChange={(event) => setModel(event.target.value)}
          placeholder="product-model"
        />
      </label>

      <button className="button primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? busyLabel : actionLabel}
      </button>
    </form>
  );
}
