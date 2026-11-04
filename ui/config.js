/*
 * Environment overlay.
 *
 * CloudFormation deployments can replace this file at publish time with:
 *   window.ADOP_RUNTIME_CONFIG = { apiBase: "/api/v1" };
 * The default keeps the UI same-origin and contains no credentials.
 */
window.ADOP_RUNTIME_CONFIG = window.ADOP_RUNTIME_CONFIG || {
  apiBase: "/api/v1",
};
