// What a tab says while it reads the first time (Talpy Den, Projects,
// Permissions, Recap): a spinner beside its sentence, as Plasma's tabs
export function Reading({ text }: { text: string }) {
  return (
    <div class="reading muted" role="status">
      <span class="spinner" aria-hidden="true" />
      <span>{text}</span>
    </div>
  );
}
