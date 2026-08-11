export function buildIdentityMatches(frontendBuildId, config) {
  return typeof config?.build_id === "string" && config.build_id === frontendBuildId;
}
