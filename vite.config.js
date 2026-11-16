import { resolve } from 'node:path'
import { defineConfig } from 'vite'

const projectRoot = import.meta.dirname
const repositoryName = process.env.GITHUB_REPOSITORY?.split('/')[1]

const apiProxy = {
  '/api': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
  '/invoice': {
    target: 'http://127.0.0.1:8000',
    changeOrigin: true,
  },
}

export default defineConfig({
  root: resolve(projectRoot, 'public'),
  publicDir: false,
  base: process.env.GITHUB_ACTIONS === 'true' && repositoryName
    ? `/${repositoryName}/`
    : '/',
  resolve: {
    alias: {
      vue: 'vue/dist/vue.esm-bundler.js',
    },
  },
  server: {
    host: '127.0.0.1',
    proxy: apiProxy,
  },
  preview: {
    proxy: apiProxy,
  },
  build: {
    outDir: resolve(projectRoot, 'dist'),
    emptyOutDir: true,
  },
})
