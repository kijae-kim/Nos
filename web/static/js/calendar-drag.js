// 큰 달력(넓은 화면)에서 일정을 끌어 다른 날 칸에 놓아 옮긴다. 폰 달력에는 끌 것이 없다.
// 새 시작일 = 시작일 + (놓은 칸 − 집은 칸). 옮긴 뒤 끝나는 날이 오늘보다 전이 되는 칸은 놓을 수 없다.
(function () {
  "use strict";
  var DAY = 86400000;

  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  // "YYYY-MM-DD" 를 날짜 수로 (시간대와 상관없이 하루 단위로 비교)
  function dayNum(s) {
    var p = s.split("-").map(Number);
    return Date.UTC(p[0], p[1] - 1, p[2]) / DAY;
  }
  function dayStr(n) {
    return new Date(n * DAY).toISOString().slice(0, 10);
  }
  // 오늘은 서버(서울) 기준 날짜를 쓴다. 없으면 브라우저 날짜
  function localToday() {
    var box = document.querySelector(".big-days[data-today]");
    if (box) return dayNum(box.dataset.today);
    var d = new Date();
    return Date.UTC(d.getFullYear(), d.getMonth(), d.getDate()) / DAY;
  }

  function move(id, newStart, undo) {
    return fetch("/calendar/events/" + id + "/move/", {
      method: "POST",
      credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ date: newStart, undo: !!undo }),
    }).then(function (r) {
      return r.json().catch(function () { return { ok: false }; });
    });
  }

  // 옮긴 달 화면으로 다시 불러온다 (안내와 되돌리기는 서버가 한 번 그려 준다)
  function reloadAt(day) {
    location.href = "/calendar/?month=" + day.slice(0, 7) + "&day=" + day;
  }

  function say(text) {
    var box = document.querySelector("[data-move-error]");
    if (!box) {
      box = document.createElement("p");
      box.className = "notice move-note";
      box.setAttribute("role", "alert");
      box.setAttribute("data-move-error", "");
      var cal = document.querySelector(".big-cal");
      if (cal) cal.parentNode.insertBefore(box, cal.parentNode.firstChild);
    }
    box.textContent = text;
    clearTimeout(say.timer);
    say.timer = setTimeout(function () { box.remove(); }, 4000);
  }

  var cells = Array.prototype.slice.call(document.querySelectorAll(".big-days [data-drop-date]"));
  var drag = null; // { id, start, grab, span }

  // 끄는 동안: 놓을 수 없는 칸을 흐리게
  function markCells() {
    var today = localToday();
    cells.forEach(function (c) {
      var newStart = drag.start + (dayNum(c.dataset.dropDate) - drag.grab);
      c.classList.toggle("no-drop", newStart + drag.span - 1 < today);
    });
  }
  function clearCells() {
    cells.forEach(function (c) { c.classList.remove("no-drop", "drop-over"); });
  }

  document.querySelectorAll('.big-days [draggable="true"][data-event-id]').forEach(function (piece) {
    piece.addEventListener("dragstart", function (e) {
      drag = {
        id: piece.dataset.eventId,
        start: dayNum(piece.dataset.start),
        grab: dayNum(piece.dataset.grabDate),
        span: Number(piece.dataset.span) || 1,
      };
      e.dataTransfer.effectAllowed = "move";
      e.dataTransfer.setData("text/plain", piece.textContent);
      piece.classList.add("dragging");
      markCells();
    });
    piece.addEventListener("dragend", function () {
      piece.classList.remove("dragging");
      clearCells();
      drag = null;
    });
    // 끌었다 놓을 때 칸 링크가 열리지 않게
    piece.addEventListener("click", function (e) { if (piece.classList.contains("dragging")) e.preventDefault(); });
  });

  cells.forEach(function (cell) {
    cell.addEventListener("dragover", function (e) {
      if (!drag || cell.classList.contains("no-drop")) return;
      e.preventDefault(); // 놓을 수 있다는 뜻
      e.dataTransfer.dropEffect = "move";
      cell.classList.add("drop-over");
    });
    cell.addEventListener("dragleave", function () { cell.classList.remove("drop-over"); });
    cell.addEventListener("drop", function (e) {
      e.preventDefault();
      if (!drag || cell.classList.contains("no-drop")) return;
      var shift = dayNum(cell.dataset.dropDate) - drag.grab;
      if (!shift) return clearCells();
      var newStart = dayStr(drag.start + shift);
      move(drag.id, newStart).then(function (data) {
        if (data.ok) reloadAt(data.date);
        else say(data.error || "옮기지 못했어요. 잠시 뒤 다시 해 볼까요?");
      }).catch(function () { say("옮기지 못했어요. 잠시 뒤 다시 해 볼까요?"); });
    });
  });

  // 되돌리기: 옛 시작일로 다시 옮긴다
  var undo = document.querySelector("[data-undo-event]");
  if (undo) undo.addEventListener("click", function () {
    undo.disabled = true;
    move(undo.dataset.undoEvent, undo.dataset.undoDate, true).then(function (data) {
      if (data.ok) reloadAt(data.date);
      else { undo.disabled = false; say(data.error || "되돌리지 못했어요. 잠시 뒤 다시 해 볼까요?"); }
    }).catch(function () { undo.disabled = false; say("되돌리지 못했어요. 잠시 뒤 다시 해 볼까요?"); });
  });
})();
