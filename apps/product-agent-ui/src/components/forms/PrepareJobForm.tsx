import { type FormEvent, useEffect, useState } from "react";
import type { PrepareJobRequest } from "../../api/types";

interface PrepareJobFormProps {
  actionLabel?: string;
  busyLabel?: string;
  isSubmitting: boolean;
  error: string | null;
  onSubmit: (request: PrepareJobRequest) => void;
  initialForm?: PrepareFormState;
  onFormChange?: (form: PrepareFormState) => void;
}

export interface PrepareFormState {
  model: string;
  url: string;
  photos: string;
  sections: string;
  skroutz_status: boolean;
  boxnow: boolean;
  price: string;
}

export const initialPrepareFormState: PrepareFormState = {
  model: "",
  url: "",
  photos: "",
  sections: "",
  skroutz_status: false,
  boxnow: false,
  price: "",
};

function parseWholeNumber(value: string): number | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return null;
  }

  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

export function PrepareJobForm({
  actionLabel = "Start prepare job",
  busyLabel = "Starting prepare job...",
  isSubmitting,
  error,
  onSubmit,
  initialForm,
  onFormChange,
}: PrepareJobFormProps) {
  const [form, setForm] = useState<PrepareFormState>(initialForm ?? initialPrepareFormState);
  const [localError, setLocalError] = useState<string | null>(null);

  useEffect(() => {
    setForm(initialForm ?? initialPrepareFormState);
  }, [initialForm]);

  useEffect(() => {
    onFormChange?.(form);
  }, [form, onFormChange]);

  function updateField<Key extends keyof PrepareFormState>(
    key: Key,
    value: PrepareFormState[Key],
  ) {
    setForm((current) => ({ ...current, [key]: value }));
  }

  function handleSubmit(event: FormEvent<HTMLFormElement>) {
    event.preventDefault();
    setLocalError(null);

    const model = form.model.trim();
    const url = form.url.trim();
    if (model.length === 0 || url.length === 0) {
      setLocalError("Model and URL are required.");
      return;
    }

    const price = form.price.trim().length === 0 ? null : Number(form.price);
    if (price !== null && Number.isNaN(price)) {
      setLocalError("Price must be a number.");
      return;
    }

    const photos = parseWholeNumber(form.photos);
    if (photos === null) {
      setLocalError("Photos must be a whole number.");
      return;
    }

    const sections = parseWholeNumber(form.sections);
    if (sections === null) {
      setLocalError("Sections must be a whole number.");
      return;
    }

    onSubmit({
      model,
      url,
      photos,
      sections,
      skroutz_status: form.skroutz_status ? 1 : 0,
      boxnow: form.boxnow ? 1 : 0,
      price,
    });
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
          value={form.model}
          onChange={(event) => updateField("model", event.target.value)}
          placeholder="product-model"
        />
      </label>

      <label>
        <span>URL</span>
        <input
          required
          type="url"
          value={form.url}
          onChange={(event) => updateField("url", event.target.value)}
          placeholder="https://example.com/product"
        />
      </label>

      <label>
        <span>Photos</span>
        <input
          inputMode="numeric"
          min="0"
          step="1"
          type="number"
          value={form.photos}
          onChange={(event) => updateField("photos", event.target.value)}
          placeholder="7"
        />
      </label>

      <label>
        <span>Sections</span>
        <input
          inputMode="numeric"
          min="0"
          step="1"
          type="number"
          value={form.sections}
          onChange={(event) => updateField("sections", event.target.value)}
          placeholder="7"
        />
      </label>

      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={form.skroutz_status}
          onChange={(event) => updateField("skroutz_status", event.target.checked)}
        />
        <span>Skroutz status</span>
      </label>

      <label className="checkbox-row">
        <input
          type="checkbox"
          checked={form.boxnow}
          onChange={(event) => updateField("boxnow", event.target.checked)}
        />
        <span>BoxNow</span>
      </label>

      <label>
        <span>Price</span>
        <input
          inputMode="decimal"
          value={form.price}
          onChange={(event) => updateField("price", event.target.value)}
          placeholder="0.00"
        />
      </label>

      <button className="button primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? busyLabel : actionLabel}
      </button>
    </form>
  );
}
