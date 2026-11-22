// 캘린더 날짜 팝업: 날짜를 누르면(폰은 꾹 눌러도) 그날 일정과 빠른 추가 칸을 서버에서 받아 보여 준다.
// 스크립트가 없으면 칸 링크(일정 추가 화면)가 그대로 동작한다.
(function () {
  "use strict";
  var sheet = document.querySelector(".day-sheet");
  var body = sheet && sheet.querySelector("[data-popup-body]");
  if (!sheet || !body || typeof sheet.showModal !== "function") return; // dialog 를 못 쓰면 링크 그대로

  var lastDragEnd = 0; // 끌어서 옮긴 직후의 누름은 팝업으로 보지 않는다
  document.addEventListener("dragend", function () { lastDragEnd = Date.now(); }, true);
  document.addEventListener("drop", function () { lastDragEnd = Date.now(); }, true);

  var openedAt = 0;
  // 로그인 화면으로 보내되, 다시 로그인하면 팝업 조각이 아니라 지금 캘린더로 돌아오게
  function toLogin(url) {
    var u = new URL(url, location.href);
    u.searchParams.set("next", location.pathname + location.search);
    location.href = u.pathname + u.search;
  }
  function failed() {
    body.innerHTML = '<p class="day-popup-loading">불러오지 못했어요. 잠시 뒤 다시 해 볼까요?</p>';
  }
  function open(url) {
    body.innerHTML = '<p class="day-popup-loading">불러오고 있어요…</p>';
    openedAt = Date.now();
    if (!sheet.open) sheet.showModal();
    fetch(url, { credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
      .then(function (r) {
        if (r.redirected) { toLogin(r.url); throw new Error("redirect"); } // 로그인이 끝났으면 로그인 화면으로
        if (!r.ok) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) { body.innerHTML = html; wire(); })
      .catch(failed);
  }
  function close() { if (sheet.open) sheet.close(); }

  // 받아 온 팝업 내용에 동작 붙이기 (하루 종일·끝나는 날·이름표 넣기·저장·자세히 쓰기·닫기)
  function wire() {
    var form = body.querySelector("[data-popup-form]");
    var closeBtn = body.querySelector("[data-popup-close]");
    if (closeBtn) closeBtn.addEventListener("click", close);
    if (!form) return;
    var allDay = form.querySelector('[name="all_day"]');
    var times = form.querySelector("[data-time-fields]");
    var endDate = form.querySelector('[name="end_date"]');
    var start = form.querySelector('[name="date"]');
    var text = form.querySelector('[name="text"]');
    var sync = function () {
      var multi = !!(endDate && endDate.value && start && endDate.value !== start.value);
      if (multi) allDay.checked = true;
      allDay.disabled = multi;
      if (times) times.hidden = allDay.checked;
    };
    if (allDay) { allDay.addEventListener("change", sync); sync(); }
    if (endDate) endDate.addEventListener("change", sync);
    form.querySelectorAll("[data-insert]").forEach(function (b) {
      b.addEventListener("click", function () {
        var v = text.value.trim();
        text.value = (v ? v + " " : "") + b.dataset.insert + " ";
        text.focus();
      });
    });
    var full = body.querySelector("[data-popup-full]");
    if (full) full.addEventListener("click", function (e) {
      if (text && text.value.trim()) {
        e.preventDefault();
        location.href = full.href + "&text=" + encodeURIComponent(text.value.trim());
      }
    });
    form.addEventListener("submit", function (e) {
      e.preventDefault();
      var btn = form.querySelector('[type="submit"]');
      if (btn) btn.disabled = true;
      fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin", headers: { "X-Requested-With": "fetch" } })
        .then(function (r) {
          if (r.redirected) { toLogin(r.url); return; } // 로그인이 끝났으면 로그인 화면으로
          if (r.ok) return r.json().then(function (d) { location.href = d.url; });
          if (r.status === 400) return r.text().then(function (html) { body.innerHTML = html; wire(); }); // 입력 오류: 팝업 안에서 다시
          throw new Error(r.status); // 그 밖의 오류(403·500): 페이지를 넣지 않고 안내만
        })
        .catch(function () {
          if (btn) btn.disabled = false;
          alert("저장하지 못했어요. 잠시 뒤 다시 해 볼까요?");
        });
    });
    if (text && !("ontouchstart" in window)) text.focus(); // 폰은 자판이 갑자기 올라오지 않게
  }

  // 바깥(어두운 곳)을 누르면 닫기
  // (꾹 눌러 연 직후 손을 뗄 때 오는 클릭이 바깥에 떨어져 바로 닫히지 않게 잠깐은 무시)
  sheet.addEventListener("click", function (e) {
    if (e.target === sheet && Date.now() - openedAt > 600) close();
  });

  document.querySelectorAll("[data-day-popup]").forEach(function (cell) {
    var pressTimer = null, longOpened = false;
    cell.addEventListener("click", function (e) {
      e.preventDefault();
      if (longOpened) { longOpened = false; return; } // 꾹 눌러 이미 열었음
      if (Date.now() - lastDragEnd < 400) return; // 끌기 직후
      open(cell.dataset.dayPopup);
    });
    // 폰: 꾹 누르면 바로 열고, 기본 메뉴(링크 미리보기·복사)는 막는다
    cell.addEventListener("contextmenu", function (e) { e.preventDefault(); });
    cell.addEventListener("touchstart", function () {
      longOpened = false;
      pressTimer = setTimeout(function () { longOpened = true; open(cell.dataset.dayPopup); }, 500);
    }, { passive: true });
    ["touchend", "touchmove", "touchcancel"].forEach(function (t) {
      cell.addEventListener(t, function () { clearTimeout(pressTimer); }, { passive: true });
    });
  });
})();
