export const API_BASE_URL =
  import.meta.env.VITE_API_BASE_URL || 'https://ai-innovation-lab-grading.onrender.com'

export const PROVIDER_OPTIONS = [
  { value: 'openai', label: 'OpenAI (GPT-4o-mini)' },
  { value: 'anthropic', label: 'Anthropic (Claude Sonnet 4.5)' },
]
