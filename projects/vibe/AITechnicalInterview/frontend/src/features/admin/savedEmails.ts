const STORAGE_PREFIX = "ai-interview-saved-emails:";
const GLOBAL_KEY = "ai-interview-global-emails";
const SESSION_EMPLOYER_KEY = "ai-interview-last-employer-id";

function parseList(raw: string | null): string[] {
  if (!raw) return [];
  try {
    const parsed = JSON.parse(raw) as unknown;
    return Array.isArray(parsed) ? parsed.filter((e) => typeof e === "string") : [];
  } catch {
    return [];
  }
}

export function loadGlobalEmails(): string[] {
  return parseList(localStorage.getItem(GLOBAL_KEY));
}

export function loadPrivateEmails(employerId: string): string[] {
  return parseList(localStorage.getItem(`${STORAGE_PREFIX}${employerId}`));
}

export function loadAllSavedEmails(employerId?: string | null): string[] {
  const merged = [...loadGlobalEmails(), ...(employerId ? loadPrivateEmails(employerId) : [])];
  return [...new Set(merged.map((e) => e.trim().toLowerCase()).filter(Boolean))];
}

export function rememberEmail(email: string, employerId?: string | null): string[] {
  const normalized = email.trim().toLowerCase();
  if (!normalized) return loadAllSavedEmails(employerId);

  const global = [...new Set([normalized, ...loadGlobalEmails()])];
  localStorage.setItem(GLOBAL_KEY, JSON.stringify(global));

  if (employerId) {
    const priv = [...new Set([normalized, ...loadPrivateEmails(employerId)])];
    localStorage.setItem(`${STORAGE_PREFIX}${employerId}`, JSON.stringify(priv));
  }
  return loadAllSavedEmails(employerId);
}

/** @deprecated use rememberEmail */
export function rememberPrivateEmail(employerId: string, email: string): string[] {
  return rememberEmail(email, employerId);
}

export function saveLastEmployerId(employerId: string) {
  sessionStorage.setItem(SESSION_EMPLOYER_KEY, employerId);
}

export function loadLastEmployerId(): string | null {
  return sessionStorage.getItem(SESSION_EMPLOYER_KEY);
}
