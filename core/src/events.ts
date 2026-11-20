// A small event emitter with the shape of vscode.EventEmitter, so code that
// moves out of the extension into core/ keeps its calls as they are.

export interface Disposable { dispose(): void }
export type Event<T> = (listener: (value: T) => void) => Disposable;

export class Emitter<T> {
  private listeners = new Set<(value: T) => void>();

  // Subscribes a listener; the returned Disposable unsubscribes it.
  readonly event: Event<T> = (listener) => {
    this.listeners.add(listener);
    return { dispose: () => { this.listeners.delete(listener); } };
  };

  // Calls the listeners in the order they subscribed. (A copy is walked, so a
  // listener may unsubscribe itself while it runs.)
  fire(value: T): void {
    for (const listener of [...this.listeners]) listener(value);
  }

  dispose(): void {
    this.listeners.clear();
  }
}
