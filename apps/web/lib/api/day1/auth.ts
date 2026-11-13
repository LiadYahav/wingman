/**
 * Sign-in, served by day1 at `/api/auth`: OpenShift's OAuth code exchange and
 * the development login. The login calls answer 401 themselves, so they never
 * send the browser to /login. And each service's build, for Settings.
 */

import { api } from "@/lib/api-client";
import type { AuthCallbackResponse, AuthConfigResponse, DevLoginRequest, ServiceBuild } from "@/types";
import type { Service } from "./approvals";

const AUTH = "/api/auth";
const ON_LOGIN_PAGE = { redirectOnUnauthorized: false };

export const authApi = {
  config: () => api.get<AuthConfigResponse>(`${AUTH}/config`),
  /** Exchange OpenShift's `code` for the app's JWT. */
  callback: (code: string) => api.post<AuthCallbackResponse>(`${AUTH}/callback`, { code }, ON_LOGIN_PAGE),
  devLogin: (body: DevLoginRequest) => api.post<AuthCallbackResponse>(`${AUTH}/dev-login`, body, ON_LOGIN_PAGE),
};

/** `GET /api/day{1,2}/build`: what a service runs. */
export const serviceBuild = (service: Service) => api.get<ServiceBuild>(`/api/${service}/build`);
