// 화면이 그려지기 전에 실행해서 테마 깜빡임을 막는다.
// 저장된 값이 없으면 기기 테마(prefers-color-scheme)를 따른다.
(function () {
  try {
    var saved = localStorage.getItem("theme");
    if (saved === "light" || saved === "dark") {
      document.documentElement.dataset.theme = saved;
    }
  } catch (e) {}
})();
