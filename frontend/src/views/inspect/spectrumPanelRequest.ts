import { ApiError, isAbortError } from "../../api/errors";
import type {
  InputReferredSpectrumPayload,
  SpectrumPayload,
  SpectrumPlane,
} from "../../api/types-plots";
import { planePayload } from "./spectrumPlaneControl";

type Plots = {
  spectrum(
    name: string,
    maxPoints?: number,
    options?: { readonly signal?: AbortSignal },
  ): Promise<SpectrumPayload>;
  spectrumInputReferred?(
    name: string,
    maxPoints?: number,
    options?: { readonly signal?: AbortSignal },
  ): Promise<InputReferredSpectrumPayload>;
};

export type SpectrumRequest = {
  readonly plane: SpectrumPlane;
  readonly signal: AbortSignal;
  readonly samePair: boolean;
  isCurrent(): boolean;
};

export type SpectrumPair = {
  readonly a: SpectrumPayload;
  readonly b: SpectrumPayload | null;
  readonly plane: SpectrumPlane;
};

export function createSpectrumPanelRequests(plots: Plots, plane: () => SpectrumPlane) {
  let generation = 0;
  let controller = new AbortController();
  let last: { readonly a: string; readonly b: string | null } | null = null;
  let renderedPlane: SpectrumPlane | null = null;

  async function fetchScopePair(
    a: string,
    b: string | null,
    signal: AbortSignal,
  ): Promise<SpectrumPair> {
    const [payloadA, payloadB] = await Promise.all([
      plots.spectrum(a, undefined, { signal }),
      b === null ? Promise.resolve(null) : plots.spectrum(b, undefined, { signal }),
    ]);
    return { a: payloadA, b: payloadB, plane: "scope" };
  }

  async function fetchPair(
    a: string,
    b: string | null,
    request: SpectrumRequest,
  ): Promise<SpectrumPair> {
    if (request.plane === "scope" || plots.spectrumInputReferred === undefined) {
      return fetchScopePair(a, b, request.signal);
    }
    try {
      const [payloadA, payloadB] = await Promise.all([
        plots.spectrumInputReferred(a, undefined, { signal: request.signal }),
        b === null
          ? Promise.resolve(null)
          : plots.spectrumInputReferred(b, undefined, { signal: request.signal }),
      ]);
      return {
        a: planePayload(payloadA),
        b: payloadB === null ? null : planePayload(payloadB),
        plane: "input-referred",
      };
    } catch (error) {
      if (isAbortError(error)) throw error;
      if (!(error instanceof ApiError) || (error.status !== 404 && error.status !== 409))
        throw error;
      return fetchScopePair(a, b, request.signal);
    }
  }

  return {
    begin(a: string, b: string | null, rendered: boolean): SpectrumRequest {
      const requestedPlane = plane();
      const samePair =
        rendered && last?.a === a && last.b === b && renderedPlane === requestedPlane;
      const gen = ++generation;
      controller.abort();
      controller = new AbortController();
      last = { a, b };
      return {
        plane: requestedPlane,
        signal: controller.signal,
        samePair,
        isCurrent: () => gen === generation,
      };
    },
    fetchPair,
    fetchScopePair,
    setRenderedPlane(next: SpectrumPlane) {
      renderedPlane = next;
    },
    last: () => last,
    dispose() {
      generation += 1;
      controller.abort();
      renderedPlane = null;
    },
  };
}
