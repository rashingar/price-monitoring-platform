import { fireEvent, screen, waitFor, within } from "@testing-library/react";
import { describe, expect, it } from "vitest";
import { installMockFetch } from "../mockFetch";
import {
  productAgentFilterCategoryDetail,
  productAgentFilterRevision,
  productAgentFilterStaleRevisionError,
  productAgentFixtureRoutes,
} from "../fixtures/productAgentApi";
import { renderWithRouter } from "../renderWithRouter";

const staleRevisionMessage =
  "This filter category changed since you loaded it. Reload the category before saving.";

function categoryWithRevision(revision: string, groupName = "Χωρητικότητα") {
  const category = {
    ...productAgentFilterCategoryDetail.category,
    revision,
    groups: [
      {
        ...productAgentFilterCategoryDetail.category.groups[0],
        name: groupName,
      },
      productAgentFilterCategoryDetail.category.groups[1],
    ],
  };

  return {
    ...category,
    category,
  };
}

describe("Filters Manager revision handling", () => {
  it("renders the loaded revision and updates it after a successful write", async () => {
    const writeRevision = "writerev002233445566778899";
    const mock = installMockFetch([
      {
        method: "PATCH",
        path: "/api/filters/categories/310/groups/grp-capacity",
        response: categoryWithRevision(writeRevision, "Χωρητικότητα XL"),
      },
      ...productAgentFixtureRoutes,
    ]);

    renderWithRouter("/product-agent/filters?category_id=310");

    await expect(screen.findByText(`Revision ${productAgentFilterRevision.slice(0, 12)}`)).resolves.toBeInTheDocument();
    fireEvent.change(await screen.findByDisplayValue("Χωρητικότητα"), {
      target: { value: "Χωρητικότητα XL" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Save group" })[0]);

    await expect(screen.findByText(`Revision ${writeRevision.slice(0, 12)}`)).resolves.toBeInTheDocument();
    const writeRequest = mock.requests.find(
      (request) =>
        request.method === "PATCH" &&
        request.pathname === "/api/filters/categories/310/groups/grp-capacity",
    );
    expect(writeRequest?.body).toMatchObject({
      expected_revision: productAgentFilterRevision,
      name: "Χωρητικότητα XL",
    });
  });

  it("shows stale revision conflicts without retrying and reloads the category revision", async () => {
    let categoryLoads = 0;
    const reloadRevision = "reloadrev556677889900112233";
    const mock = installMockFetch([
      {
        method: "GET",
        path: "/api/filters/categories/310",
        response: () => {
          categoryLoads += 1;
          return categoryLoads === 1
            ? productAgentFilterCategoryDetail
            : categoryWithRevision(reloadRevision);
        },
      },
      {
        method: "PATCH",
        path: "/api/filters/categories/310/groups/grp-capacity",
        response: productAgentFilterStaleRevisionError,
      },
      ...productAgentFixtureRoutes,
    ]);

    renderWithRouter("/product-agent/filters?category_id=310");

    fireEvent.change(await screen.findByDisplayValue("Χωρητικότητα"), {
      target: { value: "Χωρητικότητα edited" },
    });
    fireEvent.click(screen.getAllByRole("button", { name: "Save group" })[0]);

    const alert = await screen.findByRole("alert");
    expect(within(alert).getByText(staleRevisionMessage)).toBeInTheDocument();
    expect(screen.getByDisplayValue("Χωρητικότητα edited")).toBeInTheDocument();

    await waitFor(() => {
      expect(
        mock.requests.filter(
          (request) =>
            request.method === "PATCH" &&
            request.pathname === "/api/filters/categories/310/groups/grp-capacity",
        ),
      ).toHaveLength(1);
    });

    fireEvent.click(within(alert).getByRole("button", { name: "Reload category" }));

    await expect(screen.findByText(`Revision ${reloadRevision.slice(0, 12)}`)).resolves.toBeInTheDocument();
    await waitFor(() => {
      expect(screen.queryByRole("alert")).not.toBeInTheDocument();
      expect(categoryLoads).toBe(2);
      expect(
        mock.requests.filter(
          (request) =>
            request.method === "PATCH" &&
            request.pathname === "/api/filters/categories/310/groups/grp-capacity",
        ),
      ).toHaveLength(1);
    });
  });
});
