import { defineConfig } from 'tsup';

export default defineConfig([
  // NPM package build (ESM/CJS)
  {
    entry: {
      index: 'src/index.ts',
      react: 'src/adapters/react.ts',
      vue: 'src/adapters/vue.ts',
      'inject/event_bridge': 'src/inject/event_bridge.ts',
    },
    format: ['esm', 'cjs'],
    dts: { entry: { index: 'src/index.ts', react: 'src/adapters/react.ts', vue: 'src/adapters/vue.ts' } },
    clean: true,
    outDir: 'dist',
    splitting: false,
    sourcemap: true,
    treeshake: true,
    external: ['react', 'vue'],
  },
]);
