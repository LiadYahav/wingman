import { Building2 } from "lucide-react";
import { Callout, InlineCode, SectionHeader, TermCard } from "./docs-parts";

/** The two workspaces and what each holds, in the sidebar's order (ADR-0067). */
const WORKSPACES = [
  {
    title: "Customers",
    desc: "The tenants' side, and all a Viewer ever has: the Dashboard, Clusters (the tenants' hosted clusters), Flavors, Addons, Approvals, Audit and Lints, then Documentation and Settings.",
  },
  {
    title: "Infrastructure (admins)",
    desc: "What serves the customers: its Overview, Customer MCEs by site (each opens its servers in Inventory Management), Seeds & KV Clusters, Inventory Management, Quick Links, and links to Segments Manager's and Server Scan's own UIs.",
  },
] as const;

/** The kinds of cluster, as the platform's naming convention tells them apart. */
const KINDS = [
  { title: "Customer MCE", desc: "ocp4-<lc>-mce-<site>-<id>: a hub whose hosted clusters are the tenants'. Placement picks among them for a new cluster." },
  { title: "Seed", desc: "ocp4-<lc>-seed-<site>-<zone>-<id>: an MCE-level folder of the day1 repo that hosts one zone's KV clusters, never a tenant's." },
  { title: "KV cluster", desc: "ocp4-<lc>-kv-<site>-<zone>-<id>: a hosted cluster in a seed's folder, whose workers host the tenants' VM workers." },
  { title: "Tenant hosted cluster", desc: "Every other cluster file: a customer's, named by its flavor." },
] as const;

/** The docs page's "Workspaces" section, `#workspaces` (ADR-0067). */
export function WorkspacesSection() {
  return (
    <section>
      <SectionHeader id="workspaces" icon={Building2} title="Workspaces" subtitle="Customers for the tenants' side, Infrastructure for what serves them" />
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        An Admin&apos;s top bar switches between two workspaces, each with its own sidebar; Documentation and Settings are
        in both and keep the workspace you came from. A Viewer is always in Customers and sees no switch: the MCEs, the
        seeds, the KV clusters and the inventory are never shown to them, and Wingman&apos;s services refuse them too.
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
        {WORKSPACES.map(({ title, desc }) => <TermCard key={title} title={title} desc={desc} />)}
      </div>
      <h3 className="text-base font-semibold mb-3">The kinds of cluster</h3>
      <p className="text-sm text-muted-foreground leading-relaxed mb-4">
        The platform&apos;s naming convention reserves <InlineCode>mce</InlineCode>, <InlineCode>seed</InlineCode> and{" "}
        <InlineCode>kv</InlineCode> as cluster flavors, so Wingman tells each folder and file of the day1 repo apart by its
        name (<InlineCode>&lt;lc&gt;</InlineCode> is prod, prep or test):
      </p>
      <div className="grid grid-cols-1 sm:grid-cols-2 gap-3 mb-5">
        {KINDS.map(({ title, desc }) => <TermCard key={title} title={title} desc={desc} />)}
      </div>
      <div className="space-y-3">
        <Callout type="info" title="A KV cluster is managed like any hosted cluster">
          It opens on the cluster page, from Seeds &amp; KV Clusters, with the same Edit, Scale, Uninstall and Upgrade.
          Only <strong>Delete</strong> differs: it says the tenants&apos; VMs it hosts go with it, and asks you to type the
          cluster&apos;s name before it opens the merge request.
        </Callout>
        <Callout type="info" title="Create MCE is a preview">
          Customer MCEs&apos; <strong>Create MCE</strong> shows what creating one will ask for and do on the platform&apos;s
          design: the site, the lifecycle, the OpenShift version and the workers per zone; the name,{" "}
          <InlineCode>ocp4-&lt;lc&gt;-mce-&lt;site&gt;-&lt;id&gt;</InlineCode> with the site&apos;s next free letter; a master
          VM in each of the site&apos;s seed zones and the workers spread over them, every VM a{" "}
          <InlineCode>kv32</InlineCode>; and the steps, from creating the VMs to its day1 folder. Its Create stays disabled:
          a Customer MCE is installed by hand today (the platform&apos;s procedure 12), and nothing in the preview is sent
          or written.
        </Callout>
        <Callout type="tip" title="Names the workflows read today">
          The platform&apos;s workflows still look for a seed named <InlineCode>ocp4-seed-&lt;site&gt;-&lt;zone&gt;</InlineCode>{" "}
          and KV clusters named <InlineCode>ocp4-kubevirt-&lt;site&gt;-&lt;zone&gt;</InlineCode>. Wingman recognises those
          too, and a seed named <InlineCode>ocp4-&lt;lc&gt;-mce-seed-&lt;site&gt;-&lt;id&gt;</InlineCode> (whose name gives
          no zone), and marks them off-convention; every file in a seed&apos;s folder is a KV cluster, as the workflows list
          them.
        </Callout>
        <Callout type="info" title="Segments Manager and Server Scan">
          The team keeps both apart from Wingman: Infrastructure&apos;s sidebar links to each one&apos;s own UI, in a new
          tab, once your operator has set it up. A node&apos;s server on the Nodes tab still opens its page in Server Scan.
        </Callout>
      </div>
    </section>
  );
}
