// Backend base URL. Set NEXT_PUBLIC_API_URL (see .env.example) to point the UI at another host.
export const API_URL = (process.env.NEXT_PUBLIC_API_URL || 'http://localhost:8000').replace(/\/$/, '');
