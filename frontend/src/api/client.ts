import axios from "axios";

const TOKEN_KEY = "mentora_token";
const SESSION_EXPIRED_KEY = "mentora_session_expired";

export const getToken = () => localStorage.getItem(TOKEN_KEY);
export const setToken = (token: string) => localStorage.setItem(TOKEN_KEY, token);
export const clearToken = () => localStorage.removeItem(TOKEN_KEY);

export const getSessionExpired = () =>
  sessionStorage.getItem(SESSION_EXPIRED_KEY) === "1";
export const clearSessionExpired = () =>
  sessionStorage.removeItem(SESSION_EXPIRED_KEY);

export const apiClient = axios.create({ baseURL: "/api", timeout: 30000 });

apiClient.interceptors.request.use((config) => {
  const token = getToken();
  if (token) {
    config.headers.Authorization = `Bearer ${token}`;
  }
  return config;
});

apiClient.interceptors.response.use(
  (response) => response,
  (error) => {
    if (error.response?.status === 401) {
      clearToken();
      if (window.location.pathname !== "/login") {
        sessionStorage.setItem(SESSION_EXPIRED_KEY, "1");
        window.location.href = "/login";
      }
    }
    return Promise.reject(error);
  }
);
