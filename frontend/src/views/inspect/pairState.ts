export interface PairStateValue {
  readonly a: string | null;
  readonly b: string | null;
}

export interface PairStateHandle {
  get(): PairStateValue;
  pick(sessionId: string): void;
  swap(): void;
  subscribe(listener: () => void): () => void;
}

export function createPairState(): PairStateHandle {
  let a: string | null = null;
  let b: string | null = null;
  const listeners = new Set<() => void>();

  const notify = (): void => {
    for (const listener of listeners) {
      listener();
    }
  };

  return {
    get(): PairStateValue {
      return { a, b };
    },
    pick(sessionId: string): void {
      if (sessionId === a || sessionId === b) {
        return;
      }
      if (a === null) {
        a = sessionId;
      } else if (b === null) {
        b = sessionId;
      } else {
        b = sessionId;
      }
      notify();
    },
    swap(): void {
      if (b === null) {
        return;
      }
      const prevA = a;
      a = b;
      b = prevA;
      notify();
    },
    subscribe(listener: () => void): () => void {
      listeners.add(listener);
      return () => {
        listeners.delete(listener);
      };
    },
  };
}
