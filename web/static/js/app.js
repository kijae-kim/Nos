// 공통 동작: 팔레트·화면 모드 선택, + 버튼, 탭 전환형 선택, 초대 코드 칸, 숫자 세기
(function () {
  var root = document.documentElement;
  var $$ = function (selector, scope) {
    return Array.prototype.slice.call((scope || document).querySelectorAll(selector));
  };
  var store = function (key, value) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (e) {}
  };

  // 팔레트 (배 / 여정)
  function markPalette() {
    $$("[data-palette-choice]").forEach(function (b) {
      b.classList.toggle("on", b.dataset.paletteChoice === root.dataset.theme);
    });
  }
  $$("[data-palette-choice]").forEach(function (b) {
    b.addEventListener("click", function () {
      root.dataset.theme = b.dataset.paletteChoice;
      store("palette", b.dataset.paletteChoice);
      markPalette();
    });
  });
  markPalette();

  // 화면 모드 (기기 설정 / 라이트 / 다크)
  var systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  function applyMode(choice) {
    var mode = choice === "system" ? (systemDark.matches ? "dark" : "light") : choice;
    root.dataset.mode = mode;
    store("mode", choice === "system" ? null : choice);
    $$("[data-mode-choice]").forEach(function (b) {
      var on = b.dataset.modeChoice === choice;
      b.classList.toggle("on", on);
      b.setAttribute("aria-checked", String(on));
    });
  }
  var savedMode = (function () {
    try { return localStorage.getItem("mode") || "system"; } catch (e) { return "system"; }
  })();
  $$("[data-mode-choice]").forEach(function (b) {
    b.addEventListener("click", function () { applyMode(b.dataset.modeChoice); });
  });
  applyMode(savedMode);

  // + 버튼: 빠른 추가 메뉴 열고 닫기
  var app = document.getElementById("app");
  var fab = document.getElementById("fab");
  var dim = document.getElementById("dim");
  function setOpen(open) {
    app.classList.toggle("open", open);
    fab.setAttribute("aria-expanded", String(open));
  }
  if (fab) fab.addEventListener("click", function () { setOpen(!app.classList.contains("open")); });
  if (dim) dim.addEventListener("click", function () { setOpen(false); });

  // 탭 전환형 선택 (연결 방식 등): data-tabs 안의 버튼은 data-target 패널을 연다
  $$("[data-tabs]").forEach(function (group) {
    var buttons = $$("button", group);
    buttons.forEach(function (b, i) {
      b.addEventListener("click", function () {
        buttons.forEach(function (x) { x.classList.toggle("on", x === b); });
        var thumb = group.querySelector(".thumb");
        if (thumb) thumb.style.transform = "translateX(" + i * 100 + "%)";
        var target = b.dataset.target;
        $$(".view").forEach(function (panel) {
          if (panel.parentElement === group.parentElement) panel.classList.toggle("on", panel.id === target);
        });
      });
    });
  });

  // 초대 코드 6칸: 한 글자 입력하면 다음 칸으로, 지우면 이전 칸으로. 숨은 입력에 합쳐서 보낸다.
  $$("[data-code-inputs]").forEach(function (wrap) {
    var boxes = $$("input", wrap);
    var hidden = document.getElementById("code-hidden");
    function sync() {
      if (hidden) hidden.value = boxes.map(function (x) { return x.value; }).join("").toUpperCase();
    }
    // 저장된 값(다시 렌더링된 경우)을 칸에 채운다
    if (hidden && hidden.value) {
      hidden.value.split("").forEach(function (ch, i) { if (boxes[i]) boxes[i].value = ch; });
    }
    boxes.forEach(function (box, i) {
      box.addEventListener("input", function () {
        box.value = box.value.slice(-1).toUpperCase();
        if (box.value && boxes[i + 1]) boxes[i + 1].focus();
        sync();
      });
      box.addEventListener("keydown", function (e) {
        if (e.key === "Backspace" && !box.value && boxes[i - 1]) boxes[i - 1].focus();
      });
      box.addEventListener("paste", function (e) {
        var text = (e.clipboardData || window.clipboardData).getData("text").replace(/\s/g, "");
        if (!text) return;
        e.preventDefault();
        text.slice(0, boxes.length).toUpperCase().split("").forEach(function (ch, j) { boxes[j].value = ch; });
        var next = boxes[Math.min(text.length, boxes.length) - 1];
        if (next) next.focus();
        sync();
      });
    });
    wrap.closest("form").addEventListener("submit", sync);
  });

  // 초대 코드 복사
  $$("[data-copy]").forEach(function (button) {
    button.addEventListener("click", function () {
      if (!navigator.clipboard) return;
      navigator.clipboard.writeText(button.dataset.copy).then(function () {
        var label = button.textContent;
        button.textContent = "복사했어요";
        setTimeout(function () { button.textContent = label; }, 1500);
      });
    });
  });

  // 되돌리기 어려운 동작은 한 번 더 확인
  $$("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  // D-day 숫자가 올라가는 효과 (처음 열 때와 카드를 누를 때)
  function countUp(card) {
    var num = card.querySelector("[data-count]");
    if (!num || window.matchMedia("(prefers-reduced-motion: reduce)").matches) return;
    var target = parseInt(num.dataset.count, 10);
    var from = Math.max(0, target - 35);
    var start = performance.now();
    (function tick(now) {
      var t = Math.min(1, (now - start) / 1400);
      var eased = 1 - Math.pow(1 - t, 3);
      num.textContent = Math.round(from + (target - from) * eased);
      if (t < 1) requestAnimationFrame(tick);
    })(start);
  }
  $$(".dday").forEach(function (card) {
    countUp(card);
    card.addEventListener("click", function () {
      card.classList.remove("sailing");
      void card.offsetWidth; // 애니메이션을 다시 시작한다
      card.classList.add("sailing");
      countUp(card);
    });
  });

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }
})();
