import { fireEvent, render, screen } from "@testing-library/react";
import { describe, expect, it, vi } from "vitest";
import {
  initialPrepareFormState,
  PrepareJobForm,
  type PrepareFormState,
} from "../../components/forms/PrepareJobForm";

function renderPrepareForm(onSubmit = vi.fn()) {
  render(
    <PrepareJobForm
      error={null}
      isSubmitting={false}
      onSubmit={onSubmit}
    />,
  );
  return onSubmit;
}

describe("PrepareJobForm contract", () => {
  it("shows backend-valid prepare defaults", () => {
    renderPrepareForm();

    expect(screen.getByLabelText("Photos")).toHaveValue(1);
    expect(screen.getByLabelText("Sections")).toHaveValue(0);
    expect(screen.getByLabelText("Price")).toHaveValue("0");
  });

  it("never submits price as null", () => {
    const onSubmit = renderPrepareForm();

    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "005606" } });
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://example.invalid/product" } });
    fireEvent.change(screen.getByLabelText("Price"), { target: { value: "" } });
    fireEvent.submit(screen.getByRole("button", { name: "Start prepare job" }).closest("form")!);

    expect(onSubmit).toHaveBeenCalledWith(
      expect.objectContaining({
        price: 0,
      }),
    );
  });

  it("resolves empty numeric fields to backend-valid defaults", () => {
    const onSubmit = vi.fn();
    const legacyEmptyForm: PrepareFormState = {
      ...initialPrepareFormState,
      model: "005606",
      url: "https://example.invalid/product",
      photos: "",
      sections: "",
      price: "",
    };

    render(
      <PrepareJobForm
        error={null}
        initialForm={legacyEmptyForm}
        isSubmitting={false}
        onSubmit={onSubmit}
      />,
    );
    fireEvent.submit(screen.getByRole("button", { name: "Start prepare job" }).closest("form")!);

    expect(onSubmit).toHaveBeenCalledWith({
      model: "005606",
      url: "https://example.invalid/product",
      photos: 1,
      sections: 0,
      skroutz_status: 0,
      boxnow: 0,
      price: 0,
    });
  });

  it("requires a six-digit model code", () => {
    const onSubmit = renderPrepareForm();

    fireEvent.change(screen.getByLabelText("Model"), { target: { value: "00000" } });
    fireEvent.change(screen.getByLabelText("URL"), { target: { value: "https://example.invalid/product" } });
    fireEvent.submit(screen.getByRole("button", { name: "Start prepare job" }).closest("form")!);

    expect(screen.getByRole("alert")).toHaveTextContent("Model must be a 6-digit code.");
    expect(onSubmit).not.toHaveBeenCalled();
  });
});
