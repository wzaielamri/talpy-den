// A small event emitter with the shape of vscode.EventEmitter, so code that
// moves out of the extension into core/ keeps its calls as they are, and
// delivers as it does.

export interface Disposable { dispose(): void }
export type Event<T> = (listener: (value: T) => void) => Disposable;

// One subscription (the same function subscribed twice is two)
interface Listener<T> { call: (value: T) => void }

// An event on its way to the listeners subscribed when it was fired; next: the one it reaches next
interface Delivery<T> { value: T; to: Listener<T>[]; next: number }

export class Emitter<T> {
  private listeners = new Set<Listener<T>>();
  private delivering: Delivery<T> | undefined;

  // Subscribes a listener; the returned Disposable unsubscribes it.
  readonly event: Event<T> = (call) => {
    const listener = { call };
    this.listeners.add(listener);
    return { dispose: () => { this.listeners.delete(listener); } };
  };

  // Calls the listeners in the order they subscribed, as vscode.EventEmitter
  // does: one unsubscribed meanwhile (by a listener before it) isn't called,
  // one subscribed meanwhile hears the next fire. A fire from inside a listener
  // first delivers the event being delivered to the rest of its listeners,
  // then its own to every listener, before it returns: each listener hears
  // the events in the order they were fired. A listener that throws is
  // reported and doesn't stop the rest.
  fire(value: T): void {
    if (this.delivering) this.deliver(this.delivering);
    const delivery = { value, to: [...this.listeners], next: 0 };
    this.delivering = delivery;
    this.deliver(delivery);
  }

  dispose(): void {
    this.listeners.clear();
  }

  private deliver(delivery: Delivery<T>): void {
    while (delivery.next < delivery.to.length) {
      const listener = delivery.to[delivery.next++]; // (moved on before the call: it may fire again)
      if (!this.listeners.has(listener)) continue;
      try {
        listener.call(delivery.value);
      } catch (err) {
        console.error("Error in an event listener:", err);
      }
    }
    if (this.delivering === delivery) this.delivering = undefined;
  }
}
