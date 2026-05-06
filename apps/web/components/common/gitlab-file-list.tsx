import { FileText } from "lucide-react";

export interface GitLabFileGroup {
  label: string;
  files: string[];
}

export function GitLabFileList({ groups }: { groups: GitLabFileGroup[] }) {
  return (
    <div className="border-t pt-3 space-y-3">
      <p className="text-xs font-sans font-semibold text-muted-foreground uppercase tracking-wide">
        Files Created in GitLab
      </p>
      {groups.map((group) => (
        <div key={group.label} className="space-y-1">
          <p className="text-xs font-sans font-medium text-muted-foreground">{group.label}</p>
          <div className="space-y-1 pl-2">
            {group.files.map((path) => (
              <div key={path} className="flex items-start gap-2">
                <FileText className="h-3.5 w-3.5 text-primary/60 mt-0.5 shrink-0" />
                <p className="text-xs break-all text-foreground/80">{path}</p>
              </div>
            ))}
          </div>
        </div>
      ))}
    </div>
  );
}
