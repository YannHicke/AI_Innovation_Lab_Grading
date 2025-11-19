import { defineConfig } from 'vite'
import react from '@vitejs/plugin-react'

const repoBase = '/AI_Innovation_Lab_Grading/'

// https://vite.dev/config/
export default defineConfig({
  plugins: [react()],
  base: process.env.GITHUB_ACTIONS ? repoBase : '/',
})
