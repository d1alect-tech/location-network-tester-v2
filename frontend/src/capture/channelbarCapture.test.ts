import { afterEach, describe, expect, it } from "vitest";
import { CHANNELBAR_DASH } from "../components/channelbar/channelbar";
import { createChannelbar } from "../components/channelbar/channelbar";
import { mountCaptureChannelbar, paintCaptureChannelbar } from "./channelbarCapture";
import type { ModeFormHandle } from "./modeForm";
import { DEFAULT_FORM_VALUES } from "./modes";

function stubForm(): { form: ModeFormHandle; fires: Array<() => void> } {
  const fires: Array<() => void> = [];
  const form = {
    values: () => ({ ...DEFAULT_FORM_VALUES }),
    onChange: (listener: () => void) => {
      fires.push(listener);
    },
  } as unknown as ModeFormHandle;
  return { form, fires };
}

afterEach(() => {
  window.localStorage.clear();
  window.history.replaceState(null, "", window.location.pathname);
});

describe("paintCaptureChannelbar", () => {
  it("проекция полосы из частоты дискретизации, окно Ханн по умолчанию", () => {
    const bar = createChannelbar();
    const { form } = stubForm();
    paintCaptureChannelbar(bar, form.values());
    expect(bar.root.querySelector('[data-chbar="band"]')?.textContent).toBe("3 кГц – 3 МГц");
    expect(bar.root.querySelector('[data-chbar="window"]')?.textContent).toBe("Ханн");
    expect(bar.root.querySelector('[data-chbar="detector"]')?.textContent).toBe("Среднее");
    expect(bar.root.querySelector('[data-chbar="segments"]')?.textContent).toBe(CHANNELBAR_DASH);
    expect(bar.root.querySelector('[data-chbar="rbw"]')?.textContent).toBe(CHANNELBAR_DASH);
  });

  it("читает stored-префы RBW и окна", () => {
    window.localStorage.setItem("lnt.spectrum.rbw", "100");
    window.localStorage.setItem("lnt.spectrum.window", "flattop");
    const bar = createChannelbar();
    const { form } = stubForm();
    paintCaptureChannelbar(bar, form.values());
    expect(bar.root.querySelector('[data-chbar="rbw"]')?.textContent).toBe("100 Гц");
    expect(bar.root.querySelector('[data-chbar="window"]')?.textContent).toBe("Флэт-топ");
  });

  it("битая частота — полоса в прочерк, остальное живо", () => {
    const bar = createChannelbar();
    paintCaptureChannelbar(bar, { ...DEFAULT_FORM_VALUES, sampleRateHz: "мусор" });
    expect(bar.root.querySelector('[data-chbar="band"]')?.textContent).toBe(CHANNELBAR_DASH);
    expect(bar.root.querySelector('[data-chbar="window"]')?.textContent).toBe("Ханн");
  });
});

describe("mountCaptureChannelbar", () => {
  it("U4: монтирует всегда, без лесов", () => {
    const { form, fires } = stubForm();
    const bar = mountCaptureChannelbar(form);
    expect(bar.root.querySelector('[data-chbar="band"]')).not.toBeNull();
    expect(fires).toHaveLength(1);
    expect(bar?.root.querySelector('[data-chbar="band"]')?.textContent).toBe("3 кГц – 3 МГц");
    window.localStorage.setItem("lnt.spectrum.rbw", "30");
    fires[0]?.();
    expect(bar?.root.querySelector('[data-chbar="rbw"]')?.textContent).toBe("30 Гц");
  });
});
