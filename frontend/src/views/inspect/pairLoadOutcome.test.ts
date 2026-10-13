/** Задача 3 (D2): единый словарь причин + PairLoadOutcome.
 * RED→GREEN: дискриминация ok/absent/failed, reason-строка из ОДНОГО словаря,
 * серверный detail после canned-префикса, честный fallback без «undefined».
 * Проза не пиннится литералами: canned-префикс берётся из единственного
 * источника (ApiError.message), диалекты сверяются identity-равенством. */

import { describe, expect, it } from "vitest";
import { ApiError } from "../../api/errors";
import { EMPTY_METERS } from "./analysisBand";
import {
  PAIR_LOAD_OK,
  REASON_NO_ARTIFACT,
  REASON_UNAVAILABLE,
  REASON_UNKNOWN,
  branchNotComputedReason,
  insufficientCyclesReason,
  namedBranchNotComputedReason,
  pairAbsent,
  pairFailed,
  pairLoadOutcomeFrom,
  reasonFromError,
} from "./pairLoadOutcome";
import { ABSENT_ARTIFACT } from "./panels/host";

describe("PairLoadOutcome: дискриминация ok/absent/failed", () => {
  it("ok не несёт reason", () => {
    expect(PAIR_LOAD_OK.kind).toBe("ok");
    expect("reason" in PAIR_LOAD_OK).toBe(false);
  });

  it("absent и failed несут reason-строку из словаря", () => {
    const absent = pairAbsent(REASON_NO_ARTIFACT);
    const failed = pairFailed(REASON_UNKNOWN);
    expect(absent.kind).toBe("absent");
    expect(failed.kind).toBe("failed");
    if (absent.kind !== "absent" || failed.kind !== "failed") throw new Error("kind mismatch");
    expect(absent.reason).toBe(REASON_NO_ARTIFACT);
    expect(failed.reason).toBe(REASON_UNKNOWN);
  });

  it("404 классифицируется absent, остальные исходы — failed", () => {
    expect(pairLoadOutcomeFrom(new ApiError("http", { status: 404 })).kind).toBe("absent");
    expect(pairLoadOutcomeFrom(new ApiError("conflict", { status: 409 })).kind).toBe("failed");
    expect(pairLoadOutcomeFrom(new ApiError("http", { status: 422 })).kind).toBe("failed");
    expect(pairLoadOutcomeFrom(new ApiError("http", { status: 500 })).kind).toBe("failed");
    expect(pairLoadOutcomeFrom(new ApiError("network")).kind).toBe("failed");
    expect(pairLoadOutcomeFrom(new ApiError("parse")).kind).toBe("failed");
    expect(pairLoadOutcomeFrom(new Error("сбой загрузки")).kind).toBe("failed");
    expect(pairLoadOutcomeFrom("не ошибка вообще").kind).toBe("failed");
  });
});

describe("reason-строка из ОДНОГО словаря", () => {
  it("409 с detail: detail отрисован ПОСЛЕ canned-префикса", () => {
    const detail = "идентификатор сессии неоднозначен: 'syn-quiet-seed6022'";
    const error = new ApiError("conflict", { status: 409, detail });
    const reason = reasonFromError(error);
    expect(error.detail).toBe(detail);
    expect(reason).toBe(`${error.message} ${detail}`);
    expect(reason.startsWith(error.message)).toBe(true);
    expect(reason.endsWith(detail)).toBe(true);
    const outcome = pairLoadOutcomeFrom(error);
    expect(outcome.reason).toBe(reason);
  });

  it("422 с detail: detail отрисован ПОСЛЕ canned-префикса", () => {
    const detail = "недопустимый ключ сессии";
    const error = new ApiError("http", { status: 422, detail });
    expect(reasonFromError(error)).toBe(`${error.message} ${detail}`);
  });

  it("500 без detail: только canned-префикс, никогда «undefined»", () => {
    const error = new ApiError("http", { status: 500 });
    expect(error.detail).toBeUndefined();
    const reason = reasonFromError(error);
    expect(reason).toBe(error.message);
    expect(reason).not.toContain("undefined");
  });

  it("строковый cause остаётся каналом detail (parseApiError-совместимость)", () => {
    const error = new ApiError("conflict", { status: 409, cause: "дубль каталога сессии" });
    expect(error.detail).toBe("дубль каталога сессии");
    expect(reasonFromError(error)).toBe(`${error.message} дубль каталога сессии`);
  });

  it("не-Error и пустое сообщение → REASON_UNKNOWN из словаря", () => {
    expect(reasonFromError(null)).toBe(REASON_UNKNOWN);
    expect(reasonFromError(42)).toBe(REASON_UNKNOWN);
    expect(reasonFromError(new Error(""))).toBe(REASON_UNKNOWN);
  });

  it("Error с сообщением → сообщение дословно (совместимо с бывшим errorMessage)", () => {
    expect(reasonFromError(new Error("обрыв связи"))).toBe("обрыв связи");
  });
});

describe("три диалекта потребляют ОДИН словарь (identity, рендеры не меняются)", () => {
  it("chips-диалект: ABSENT_ARTIFACT === REASON_NO_ARTIFACT", () => {
    expect(ABSENT_ARTIFACT).toBe(REASON_NO_ARTIFACT);
  });

  it("band-диалект: пустые метры несут REASON_UNAVAILABLE", () => {
    expect(EMPTY_METERS.length).toBeGreaterThan(0);
    expect(EMPTY_METERS.every((meter) => meter.value === REASON_UNAVAILABLE)).toBe(true);
  });

  it("билдеры фраз веток и циклов структурны: вход виден, пустое сообщение без хвоста", () => {
    // Проза не пиннится: проверяем только структуру и видимость входа билдера.
    expect(branchNotComputedReason("")).not.toContain(": ");
    expect(branchNotComputedReason("window underflow")).toContain(": window underflow");
    expect(namedBranchNotComputedReason("psd", "нет отсчётов")).toContain("psd");
    expect(namedBranchNotComputedReason("psd", "нет отсчётов")).toContain("нет отсчётов");
    expect(insufficientCyclesReason(47, 100)).toContain("47");
    expect(insufficientCyclesReason(47, 100)).toContain("100");
  });
});
