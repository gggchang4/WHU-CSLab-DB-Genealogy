import type {
  Bounds,
  DescendantMapResponse,
  Genealogy,
  MemberSummary
} from "./types";

const API_ROOT = "/api";

function getCookie(name: string) {
  const cookie = document.cookie
    .split("; ")
    .find((item) => item.startsWith(`${name}=`));
  return cookie ? decodeURIComponent(cookie.split("=").slice(1).join("=")) : "";
}

async function requestJson<T>(path: string, signal?: AbortSignal): Promise<T> {
  const response = await fetch(`${API_ROOT}${path}`, {
    credentials: "same-origin",
    signal,
    headers: {
      Accept: "application/json"
    }
  });

  if (response.status === 401) {
    window.location.href = "/accounts/login/";
    throw new Error("Authentication required.");
  }

  if (!response.ok) {
    let message = `Request failed with status ${response.status}.`;
    try {
      const payload = (await response.json()) as { error?: string };
      message = payload.error || message;
    } catch {
      // Keep the status-based message when the response is not JSON.
    }
    throw new Error(message);
  }

  return response.json() as Promise<T>;
}

export function fetchGenealogies(signal?: AbortSignal) {
  return requestJson<{ genealogies: Genealogy[] }>("/genealogies/", signal);
}

export async function logout() {
  await fetch("/accounts/logout/", {
    method: "POST",
    credentials: "same-origin",
    headers: {
      "X-CSRFToken": getCookie("csrftoken")
    }
  });
  window.location.assign("/accounts/login/");
}

export function searchMembers(
  genealogyId: number,
  query: string,
  signal?: AbortSignal
) {
  const params = new URLSearchParams();
  if (query.trim()) {
    params.set("q", query.trim());
  }
  params.set("limit", "12");
  return requestJson<{ members: MemberSummary[] }>(
    `/genealogies/${genealogyId}/members/search/?${params.toString()}`,
    signal
  );
}

export function fetchDescendantViewport(
  genealogyId: number,
  rootMemberId: number,
  maxDepth: number,
  bounds: Bounds,
  signal?: AbortSignal
) {
  const params = new URLSearchParams({
    root_member_id: String(rootMemberId),
    max_depth: String(maxDepth),
    x_min: String(Math.round(bounds.x_min)),
    x_max: String(Math.round(bounds.x_max)),
    y_min: String(Math.round(bounds.y_min)),
    y_max: String(Math.round(bounds.y_max)),
    padding: "420"
  });
  return requestJson<DescendantMapResponse>(
    `/genealogies/${genealogyId}/descendant-map/viewport/?${params.toString()}`,
    signal
  );
}
