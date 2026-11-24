/**
 * An OpenShift release tag, as a cluster file's `mastertag` writes it: the
 * release, then the architecture its image is built for (`4.16.27-x86_64`,
 * `4.16.0-rc.1-aarch64`, `4.21.40-multi`). The same rule as wingman-core's
 * `wingman_core.domain.release_tags`; day1's upgrade ladder lists releases
 * without their architecture (`4.16.27`).
 */

/** The architectures OpenShift publishes release images for, as a tag's last part. */
const ARCHES: readonly string[] = ["x86_64", "aarch64", "ppc64le", "s390x", "multi"];

/**
 * The release `tag` names: a last part that is an architecture comes off, a
 * prerelease stays (`4.16.0-rc.1-x86_64` is `4.16.0-rc.1`), and a tag with
 * any other ending is the release as written.
 */
export function withoutArch(tag: string): string {
  const dash = tag.lastIndexOf("-");
  return dash >= 0 && ARCHES.includes(tag.slice(dash + 1)) ? tag.slice(0, dash) : tag;
}

/** The entry of `offered` that `version` names (`4.18.56-x86_64` is `4.18.56`), or `null`. */
export function offeredRelease(version: unknown, offered: readonly string[]): string | null {
  if (typeof version !== "string") return null;
  const release = withoutArch(version.trim());
  return release !== "" && offered.includes(release) ? release : null;
}
