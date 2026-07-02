import type { JsonMap } from './types';

export async function fetchJson<T = any>(url: string): Promise<T> {
  const response = await fetch(url);
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(payload, response));
  return payload;
}

export async function postJson<T = any>(url: string, body: JsonMap): Promise<T> {
  const response = await fetch(url, {
    method: 'POST',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(payload, response));
  return payload;
}

export async function deleteJson<T = any>(url: string, body: JsonMap): Promise<T> {
  const response = await fetch(url, {
    method: 'DELETE',
    headers: { 'content-type': 'application/json' },
    body: JSON.stringify(body),
  });
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(payload, response));
  return payload;
}

export async function postForm<T = any>(url: string, body: FormData): Promise<T> {
  const response = await fetch(url, { method: 'POST', body });
  const payload = await readJsonResponse(response);
  if (!response.ok) throw new Error(errorMessage(payload, response));
  return payload;
}

async function readJsonResponse(response: Response) {
  const text = await response.text();
  if (!text) return null;
  try {
    return JSON.parse(text);
  } catch {
    return { error: text };
  }
}

function errorMessage(payload: any, response: Response) {
  if (payload?.error) return payload.error;
  if (payload?.detail) return typeof payload.detail === 'string' ? payload.detail : JSON.stringify(payload.detail);
  if (payload?.message) return payload.message;
  return response.statusText || `HTTP ${response.status}`;
}
