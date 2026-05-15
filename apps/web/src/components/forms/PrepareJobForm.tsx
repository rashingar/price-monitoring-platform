import { type FormEvent, useState } from "react";
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
  gallery_url: string;
  characteristics_url: string;
  second_opencart_image_index: string;
}

export const initialPrepareFormState: PrepareFormState = {
  model: "",
  url: "",
  photos: "1",
  sections: "0",
  skroutz_status: false,
  boxnow: false,
  price: "0",
  gallery_url: "",
  characteristics_url: "",
  second_opencart_image_index: "",
};

function parseWholeNumber(value: string, defaultValue: number): number | null {
  const trimmed = value.trim();
  if (trimmed.length === 0) {
    return defaultValue;
  }

  const parsed = Number(trimmed);
  return Number.isInteger(parsed) && parsed >= 0 ? parsed : null;
}

function normalizePrepareFormState(form?: PrepareFormState): PrepareFormState {
  return { ...initialPrepareFormState, ...(form ?? {}) };
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
  const isControlled = initialForm !== undefined && onFormChange !== undefined;
  const [localForm, setLocalForm] = useState<PrepareFormState>(() =>
    normalizePrepareFormState(initialForm),
  );
  const form = isControlled ? normalizePrepareFormState(initialForm) : localForm;
  const [localError, setLocalError] = useState<string | null>(null);
  const [extraSettingsOpen, setExtraSettingsOpen] = useState(false);

  function updateField<Key extends keyof PrepareFormState>(
    key: Key,
    value: PrepareFormState[Key],
  ) {
    if (isControlled) {
      onFormChange({ ...form, [key]: value });
      return;
    }

    setLocalForm((current) => ({ ...current, [key]: value }));
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
    if (!/^\d{6}$/.test(model)) {
      setLocalError("Model must be a 6-digit code.");
      return;
    }

    const priceInput = form.price.trim();
    const price = priceInput.length === 0 ? 0 : Number(priceInput);
    if (!Number.isFinite(price) || price < 0) {
      setLocalError("Price must be a number.");
      return;
    }

    const photos = parseWholeNumber(form.photos, 1);
    if (photos === null) {
      setLocalError("Photos must be a whole number.");
      return;
    }

    const sections = parseWholeNumber(form.sections, 0);
    if (sections === null) {
      setLocalError("Sections must be a whole number.");
      return;
    }

    const galleryUrl = form.gallery_url.trim();
    const characteristicsUrl = form.characteristics_url.trim();
    const secondImageIndexInput = form.second_opencart_image_index.trim();
    let secondOpenCartImageIndex: number | null = null;
    if (secondImageIndexInput.length > 0) {
      const parsedSecondOpenCartImageIndex = Number(secondImageIndexInput);
      if (!Number.isInteger(parsedSecondOpenCartImageIndex) || parsedSecondOpenCartImageIndex < 1) {
        setLocalError("Second OpenCart image index must be a positive whole number.");
        return;
      }
      secondOpenCartImageIndex = parsedSecondOpenCartImageIndex;
    }

    const request: PrepareJobRequest = {
      model,
      url,
      photos,
      sections,
      skroutz_status: form.skroutz_status ? 1 : 0,
      boxnow: form.boxnow ? 1 : 0,
      price,
    };
    if (galleryUrl.length > 0) {
      request.gallery_url = galleryUrl;
    }
    if (characteristicsUrl.length > 0) {
      request.characteristics_url = characteristicsUrl;
    }
    if (secondOpenCartImageIndex !== null) {
      request.second_opencart_image_index = secondOpenCartImageIndex;
    }
    onSubmit(request);
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

      <div className="form-extra-settings">
        <button
          aria-controls="prepare-extra-settings"
          aria-expanded={extraSettingsOpen}
          className="text-button"
          type="button"
          onClick={() => setExtraSettingsOpen((open) => !open)}
        >
          Extra settings
        </button>

        {extraSettingsOpen ? (
          <div id="prepare-extra-settings" className="form-extra-settings-fields">
            <label>
              <span>Gallery URL</span>
              <input
                type="url"
                value={form.gallery_url}
                onChange={(event) => updateField("gallery_url", event.target.value)}
                placeholder="https://example.com/product-gallery"
              />
            </label>
            <small>Optional URL used only for gallery image extraction. Product data still comes from the main URL.</small>

            <label>
              <span>Characteristics URL</span>
              <input
                type="url"
                value={form.characteristics_url}
                onChange={(event) => updateField("characteristics_url", event.target.value)}
                placeholder="https://example.com/product-specifications"
              />
            </label>
            <small>Optional URL used only for characteristics/specifications extraction. Product data still comes from the main URL unless overridden for this extraction step.</small>

            <label>
              <span>Second OpenCart image index</span>
              <input
                inputMode="numeric"
                min="1"
                step="1"
                type="number"
                value={form.second_opencart_image_index}
                onChange={(event) => updateField("second_opencart_image_index", event.target.value)}
                placeholder="4"
              />
            </label>
            <small>1-based index from the deduplicated gallery order. When valid, that image is placed second in OpenCart.</small>
          </div>
        ) : null}
      </div>

      <button className="button primary" type="submit" disabled={isSubmitting}>
        {isSubmitting ? busyLabel : actionLabel}
      </button>
    </form>
  );
}
