const TIME_ZONE = "America/Sao_Paulo";

function doGet() {
  return jsonResponse_({
    ok: true,
    service: "JARVIS Google Bridge",
    status: "online"
  });
}

function doPost(e) {
  try {
    const body = JSON.parse((e && e.postData && e.postData.contents) || "{}");
    const expectedSecret =
      PropertiesService.getScriptProperties().getProperty("BRIDGE_SECRET");

    if (!expectedSecret || body.secret !== expectedSecret) {
      return jsonResponse_({ ok: false, error: "Não autorizado" });
    }

    switch (String(body.action || "")) {
      case "calendar_list":
        return listCalendarEvents_(body);

      case "calendar_create":
        return createCalendarEvent_(body);

      case "sheet_read":
        return readClassSheet_(body);

      default:
        return jsonResponse_({ ok: false, error: "Ação desconhecida" });
    }
  } catch (error) {
    console.error(error);
    return jsonResponse_({
      ok: false,
      error: String(error && error.message ? error.message : error)
    });
  }
}

function listCalendarEvents_(body) {
  const days = Math.min(Math.max(Number(body.days || 7), 1), 31);
  const start = body.start ? new Date(body.start) : new Date();
  const end = body.end
    ? new Date(body.end)
    : new Date(start.getTime() + days * 24 * 60 * 60 * 1000);

  if (isNaN(start.getTime()) || isNaN(end.getTime()) || end <= start) {
    return jsonResponse_({ ok: false, error: "Período inválido" });
  }

  const calendar = CalendarApp.getDefaultCalendar();
  const events = calendar.getEvents(start, end).slice(0, 50).map(function(event) {
    return {
      id: event.getId(),
      title: event.getTitle(),
      start: event.getStartTime().toISOString(),
      end: event.getEndTime().toISOString(),
      allDay: event.isAllDayEvent(),
      location: event.getLocation() || "",
      description: event.getDescription() || "",
      reminders: event.getPopupReminders()
    };
  });

  return jsonResponse_({
    ok: true,
    calendar: calendar.getName(),
    timeZone: TIME_ZONE,
    events: events
  });
}

function createCalendarEvent_(body) {
  const title = String(body.title || "").trim();
  const start = new Date(body.start);
  const end = new Date(body.end);

  if (!title) {
    return jsonResponse_({ ok: false, error: "Título obrigatório" });
  }

  if (isNaN(start.getTime()) || isNaN(end.getTime()) || end <= start) {
    return jsonResponse_({ ok: false, error: "Data ou horário inválido" });
  }

  const calendar = CalendarApp.getDefaultCalendar();
  const event = calendar.createEvent(title, start, end, {
    description: String(body.description || ""),
    location: String(body.location || "")
  });

  event.removeAllReminders();

  const reminders = Array.isArray(body.reminders) ? body.reminders : [30];
  const validReminders = reminders
    .map(Number)
    .filter(function(minutes) {
      return Number.isInteger(minutes) && minutes >= 5 && minutes <= 40320;
    })
    .slice(0, 5);

  validReminders.forEach(function(minutes) {
    event.addPopupReminder(minutes);
  });

  return jsonResponse_({
    ok: true,
    created: {
      id: event.getId(),
      title: event.getTitle(),
      start: event.getStartTime().toISOString(),
      end: event.getEndTime().toISOString(),
      reminders: event.getPopupReminders()
    }
  });
}

function readClassSheet_(body) {
  const properties = PropertiesService.getScriptProperties();
  const spreadsheetId = properties.getProperty("SHEET_ID");
  const configuredTab = properties.getProperty("SHEET_TAB");

  if (!spreadsheetId) {
    return jsonResponse_({ ok: false, error: "SHEET_ID não configurado" });
  }

  const spreadsheet = SpreadsheetApp.openById(spreadsheetId);
  const requestedTab = String(body.tab || configuredTab || "").trim();
  const sheet = requestedTab
    ? spreadsheet.getSheetByName(requestedTab)
    : spreadsheet.getSheets()[0];

  if (!sheet) {
    return jsonResponse_({
      ok: false,
      error: `Aba não encontrada: ${requestedTab}`
    });
  }

  const lastRow = Math.min(sheet.getLastRow(), 300);
  const lastColumn = Math.min(sheet.getLastColumn(), 30);

  if (lastRow < 1 || lastColumn < 1) {
    return jsonResponse_({
      ok: true,
      spreadsheet: spreadsheet.getName(),
      tab: sheet.getName(),
      headers: [],
      rows: []
    });
  }

  const values = sheet
    .getRange(1, 1, lastRow, lastColumn)
    .getDisplayValues();

  return jsonResponse_({
    ok: true,
    spreadsheet: spreadsheet.getName(),
    tab: sheet.getName(),
    headers: values[0] || [],
    rows: values.slice(1)
  });
}

function jsonResponse_(data) {
  return ContentService
    .createTextOutput(JSON.stringify(data))
    .setMimeType(ContentService.MimeType.JSON);
}
