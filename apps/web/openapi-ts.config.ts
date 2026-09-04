import { defineConfig } from '@hey-api/openapi-ts';
export default defineConfig({ input: './openapi/bootstrap.openapi.json', output: './src/lib/api/generated' });
