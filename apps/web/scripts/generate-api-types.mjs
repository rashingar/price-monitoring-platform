import { generateApiTypes, generatedSpecs } from "./api-type-generation.mjs";

try {
  generateApiTypes(generatedSpecs, "output");
} catch (error) {
  console.error(error instanceof Error ? error.message : error);
  process.exit(1);
}
