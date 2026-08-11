export function filterSessions(sessions, query) {
  const normalizedQuery = String(query ?? "").trim().toLocaleLowerCase("ru");

  if (!normalizedQuery) {
    return sessions.slice();
  }

  return sessions.filter((session) => {
    const name = String(session.name ?? "").trim().toLocaleLowerCase("ru");
    const label = String(session.summary?.label ?? "")
      .trim()
      .toLocaleLowerCase("ru");

    return name.includes(normalizedQuery) || label.includes(normalizedQuery);
  });
}

export function sortSessions(sessions) {
  return [...sessions].sort((a, b) => {
    const aDate = a.summary?.created_utc ?? "";
    const bDate = b.summary?.created_utc ?? "";
    if (Boolean(aDate) !== Boolean(bDate)) {
      return aDate ? -1 : 1;
    }
    if (aDate !== bDate) {
      return aDate < bDate ? 1 : -1;
    }
    return String(a.name).localeCompare(String(b.name), "ru");
  });
}
