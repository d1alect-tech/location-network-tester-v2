export type PairSlot = "a" | "b";

export interface PairStateValue {
  readonly a: string | null;
  readonly b: string | null;
}

export interface PairStateHandle {
  get(): PairStateValue;
  pick(sessionId: string): void;
  arm(slot: PairSlot): void;
  armed(): PairSlot | null;
  assignSlot(slot: PairSlot, sessionId: string): void;
  setPair(next: PairStateValue): void;
  swap(): void;
  subscribe(listener: () => void): () => void;
}

export function createPairState(): PairStateHandle {
  let a: string | null = null;
  let b: string | null = null;
  let armedSlot: PairSlot | null = null;
  const listeners = new Set<() => void>();

  function assign(slot: PairSlot, sessionId: string): void {
    if (slot === "a") {
      if (sessionId === a) {
        armedSlot = null;
        return;
      }
      a = sessionId;
      if (b === sessionId) b = null;
    } else {
      if (sessionId === b) {
        armedSlot = null;
        return;
      }
      b = sessionId;
      if (a === sessionId) a = null;
    }
    armedSlot = null;
    notify();
  }

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
      if (armedSlot !== null) {
        assign(armedSlot, sessionId);
        return;
      }
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
    arm(slot: PairSlot): void {
      armedSlot = armedSlot === slot ? null : slot;
      notify();
    },
    armed(): PairSlot | null {
      return armedSlot;
    },
    assignSlot(slot: PairSlot, sessionId: string): void {
      assign(slot, sessionId);
    },
    setPair(next: PairStateValue): void {
      if (next.a === a && next.b === b) return;
      a = next.a;
      b = next.b;
      armedSlot = null;
      notify();
    },
    swap(): void {
      armedSlot = null;
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
