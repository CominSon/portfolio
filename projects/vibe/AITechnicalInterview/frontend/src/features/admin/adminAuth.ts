/** Хранение Basic Auth для админских API (sessionStorage). */
const STORAGE_KEY = "admin_basic_auth";

export function getAdminAuthHeader(): string | null {
  try {
    return sessionStorage.getItem(STORAGE_KEY);
  } catch {
    return null;
  }
}

export function setAdminCredentials(username: string, password: string): void {
  const token = btoa(`${username}:${password}`);
  sessionStorage.setItem(STORAGE_KEY, `Basic ${token}`);
}

export function clearAdminCredentials(): void {
  try {
    sessionStorage.removeItem(STORAGE_KEY);
  } catch {
    /* ignore */
  }
}

export function hasAdminCredentials(): boolean {
  return Boolean(getAdminAuthHeader());
}
