import type {
  CatalogCategoryHierarchyResponse,
  CatalogCategoryNode,
  CatalogFamilyNode,
} from "../api/commerceTypes";

export const CATEGORY_HIERARCHY_UNAVAILABLE_MESSAGE =
  "Category hierarchy endpoint is unavailable. Update price-fetcher backend.";

export interface HierarchyOption {
  value: string;
  count: number | null;
}

export interface HierarchySelection {
  family: string;
  categoryName: string;
  subCategory: string;
}

function normalizeCount(count: number | null | undefined): number | null {
  return typeof count === "number" && Number.isFinite(count) ? count : null;
}

function byValue(left: HierarchyOption, right: HierarchyOption): number {
  return left.value.localeCompare(right.value);
}

export function formatHierarchyOptionLabel(option: HierarchyOption): string {
  return `${option.value}${option.count === null ? "" : ` (${option.count})`}`;
}

export function getFamilyOptions(
  hierarchy: CatalogCategoryHierarchyResponse | null,
): HierarchyOption[] {
  return (hierarchy?.items ?? [])
    .filter((item) => item.family.trim().length > 0)
    .map((item) => ({ value: item.family, count: normalizeCount(item.count) }))
    .sort(byValue);
}

export function findFamilyNode(
  hierarchy: CatalogCategoryHierarchyResponse | null,
  family: string,
): CatalogFamilyNode | null {
  if (!family) {
    return null;
  }

  return hierarchy?.items.find((item) => item.family === family) ?? null;
}

export function getCategoryOptions(
  hierarchy: CatalogCategoryHierarchyResponse | null,
  family: string,
): HierarchyOption[] {
  const familyNode = findFamilyNode(hierarchy, family);
  return (familyNode?.categories ?? [])
    .filter((item) => item.category_name.trim().length > 0)
    .map((item) => ({ value: item.category_name, count: normalizeCount(item.count) }))
    .sort(byValue);
}

export function findCategoryNode(
  hierarchy: CatalogCategoryHierarchyResponse | null,
  family: string,
  categoryName: string,
): CatalogCategoryNode | null {
  if (!family || !categoryName) {
    return null;
  }

  return (
    findFamilyNode(hierarchy, family)?.categories?.find(
      (item) => item.category_name === categoryName,
    ) ?? null
  );
}

export function getSubCategoryOptions(
  hierarchy: CatalogCategoryHierarchyResponse | null,
  family: string,
  categoryName: string,
): HierarchyOption[] {
  const categoryNode = findCategoryNode(hierarchy, family, categoryName);
  return (categoryNode?.sub_categories ?? [])
    .filter((item) => item.sub_category.trim().length > 0)
    .map((item) => ({ value: item.sub_category, count: normalizeCount(item.count) }))
    .sort(byValue);
}

export function makeHierarchyFilterParams(selection: HierarchySelection): {
  family?: string;
  category_name?: string;
  sub_category?: string;
} {
  return {
    ...(selection.family ? { family: selection.family } : {}),
    ...(selection.categoryName ? { category_name: selection.categoryName } : {}),
    ...(selection.subCategory ? { sub_category: selection.subCategory } : {}),
  };
}
