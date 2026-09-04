import { defineConfig } from '@hey-api/openapi-ts';

const input = process.env.OPENAPI_INPUT?.trim();

if (!input) {
  throw new Error(
    'OPENAPI_INPUT is required and must point to an authoritative FastAPI OpenAPI URL or file',
  );
}

export default defineConfig({
  input,
  output: './src/lib/api/generated',
});
