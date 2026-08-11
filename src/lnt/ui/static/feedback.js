const STAGE_SHORT = {
  queued: "Очередь",
  checking_device: "Устройство",
  simulating: "Симуляция",
  capturing: "Захват",
  analyzing: "Анализ",
  comparing: "Сравнение",
  selftest: "Selftest",
  done: "Готово",
};

const TERMINAL_STATUSES = new Set(["succeeded", "cancelled", "failed"]);

export function adviceFor(message) {
  if (!message) return null;
  const normalized = String(message).toLowerCase();
  if (normalized.includes("слишком слаб")) {
    return "Проверьте CH2: анализу нужна опорная сеть 50 Гц — подключите трансформатор 230:6 к CH2 и повторите захват.";
  }
  if (normalized.includes("уже существует")) {
    return "Укажите другое имя в поле «Каталог» или оставьте его пустым — имя будет создано автоматически.";
  }
  if (/(устройств|драйвер|winusb|осциллограф|прошивк)/.test(normalized)) {
    return "Нажмите «Проверить устройство»: проверьте USB-кабель, драйвер WinUSB (Zadig) и прошивку.";
  }
  return null;
}

export function jobTitle(snapshot, baseTitle) {
  if (!snapshot || TERMINAL_STATUSES.has(snapshot.status)) {
    return baseTitle;
  }
  const stageShort = STAGE_SHORT[snapshot.stage] ?? "Задача";
  const total = snapshot.series_total;
  const index = snapshot.series_index;
  if (Number.isFinite(total) && total > 0 && Number.isFinite(index)) {
    return `[${index}/${total}] ${stageShort} — LNT`;
  }
  return `${stageShort} — LNT`;
}
