// 테마 선택 (기기 설정 / 라이트 / 다크)
(function () {
  var buttons = document.querySelectorAll("[data-theme-choice]");
  if (!buttons.length) return;

  function current() {
    return document.documentElement.dataset.theme || "system";
  }
  function render() {
    buttons.forEach(function (b) {
      b.setAttribute("aria-checked", String(b.dataset.themeChoice === current()));
    });
  }
  buttons.forEach(function (b) {
    b.addEventListener("click", function () {
      var choice = b.dataset.themeChoice;
      if (choice === "system") {
        delete document.documentElement.dataset.theme;
      } else {
        document.documentElement.dataset.theme = choice;
      }
      try {
        if (choice === "system") localStorage.removeItem("theme");
        else localStorage.setItem("theme", choice);
      } catch (e) {}
      render();
    });
  });
  render();
})();

// 초대 코드 복사
document.querySelectorAll("[data-copy]").forEach(function (button) {
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
document.querySelectorAll("form[data-confirm]").forEach(function (form) {
  form.addEventListener("submit", function (event) {
    if (!window.confirm(form.dataset.confirm)) event.preventDefault();
  });
});

if ("serviceWorker" in navigator) {
  navigator.serviceWorker.register("/sw.js").catch(function () {});
}
