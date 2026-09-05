import { configureApiBase } from '../../../../packages/api-client/src/core';

configureApiBase(import.meta.env.VITE_API_BASE);

export * from '../../../../packages/api-client/src/core';
