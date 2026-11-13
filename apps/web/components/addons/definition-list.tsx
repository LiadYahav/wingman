/** An add-on's facts, term beside value (the Addons pages' chart dialog and the add-on page). */
export function DefinitionList({ items }: { items: [string, React.ReactNode][] }) {
  return (
    <dl className="grid grid-cols-[9rem_minmax(0,1fr)] gap-x-3 gap-y-1.5 text-xs">
      {items.map(([term, value]) => (
        <div key={term} className="contents">
          <dt className="text-muted-foreground">{term}</dt>
          <dd className="break-all font-mono text-[11px]">{value}</dd>
        </div>
      ))}
    </dl>
  );
}
