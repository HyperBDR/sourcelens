// API configuration for the application
// Centralizes all API endpoints and base URLs

// Get base URL from environment variables
// Format: http://localhost:8000 or https://api.example.com
const getBaseUrl = () => {
  // Check if VITE_API_BASE_URL is set
  const envUrl = import.meta.env.VITE_API_BASE_URL

  if (envUrl) {
    // If VITE_API_BASE_URL includes /api, strip it
    return envUrl.endsWith('/api') ? envUrl.replace('/api', '') : envUrl
  }

  // Default for development in Docker
  return window.location.origin
}

// Get API base URL (for API endpoints)
const getApiBaseUrl = () => {
  const baseUrl = getBaseUrl()
  return `${baseUrl}/api`
}

// Get OAuth base URL (for OAuth endpoints like Google login)
// For production, use the same base URL as API
// For development without env variable, use window.location.origin
const getOAuthBaseUrl = () => {
  const envUrl = import.meta.env.VITE_API_BASE_URL
  if (envUrl) {
    return envUrl.endsWith('/api') ? envUrl.replace('/api', '') : envUrl
  }
  // Use current origin as fallback (works for both dev and production)
  return window.location.origin
}

// Get API timeout from environment variables
// Default: 30000ms (30 seconds) for production, can be overridden via VITE_API_TIMEOUT
// Format: milliseconds (e.g., 30000 for 30 seconds)
const getApiTimeout = () => {
  const envTimeout = import.meta.env.VITE_API_TIMEOUT
  if (envTimeout) {
    const parsed = parseInt(envTimeout, 10)
    if (Number.isFinite(parsed) && parsed > 0) return parsed
  }
  // Default to 30 seconds for production stability
  return 30000
}

// Export configuration
export default {
  baseUrl: getBaseUrl(),
  apiBaseUrl: getApiBaseUrl(),
  oauthBaseUrl: getOAuthBaseUrl(),
  timeout: getApiTimeout(),

  // OAuth endpoints
  endpoints: {
    googleLogin: () => `${getOAuthBaseUrl()}/accounts/google/login/`,
    wechatLogin: () => `${getOAuthBaseUrl()}/accounts/weixin/login/`,
    oauthCallback: () => `${getOAuthBaseUrl()}/accounts/oauth/callback/`
  }
}
