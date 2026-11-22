// 화면이 그려지기 전에 팔레트(배/여정)와 화면 모드(라이트/다크)를 정한다.
// 저장된 값이 없으면 기본 팔레트는 배, 화면 모드는 기기 설정을 따른다. 시작 화면을 보여 줄지도 여기서 정한다.
(function () {
  var root = document.documentElement;
  var palette = "boat";
  var mode = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  // 로그인했으면 계정에 저장한 값(서버가 html 에 적어 둔다)을 따르고, 이 기기에도 적어 둔다.
  // 그래야 로그아웃한 화면(로그인 화면 등)에서도 같은 테마로 보인다.
  var accountPalette = root.dataset.accountPalette;
  var accountMode = root.dataset.accountMode;
  try {
    if (accountPalette) localStorage.setItem("palette", accountPalette);
    if (accountMode === "system") localStorage.removeItem("mode");
    else if (accountMode) localStorage.setItem("mode", accountMode);
    var savedPalette = localStorage.getItem("palette");
    var savedMode = localStorage.getItem("mode");
    if (savedPalette === "boat" || savedPalette === "journey") palette = savedPalette;
    if (savedMode === "light" || savedMode === "dark") mode = savedMode;
  } catch (e) {
    if (accountPalette === "boat" || accountPalette === "journey") palette = accountPalette;
    if (accountMode === "light" || accountMode === "dark") mode = accountMode;
  }
  root.dataset.theme = palette;
  root.dataset.mode = mode;
  // 이 탭(또는 설치한 앱)을 처음 열었을 때만 시작 화면을 보여 준다
  try {
    if (!sessionStorage.getItem("splashed")) root.classList.add("splash-on");
  } catch (e) {}

  // 주소창·상태 표시줄 색을 지금 테마·모드의 앱 배경색(app.css 의 --bg-1)으로. 테마·모드를 바꾸면 따라 바뀐다
  var BAR = { "boat-light": "#E4EDFB", "journey-light": "#F8F0E3", "boat-dark": "#0B1026", "journey-dark": "#15111F" };
  function syncBar() {
    var meta = document.getElementById("theme-color");
    var color = BAR[root.dataset.theme + "-" + root.dataset.mode];
    if (meta && color) meta.setAttribute("content", color);
  }
  if (document.readyState === "loading") document.addEventListener("DOMContentLoaded", syncBar); else syncBar();
  try {
    new MutationObserver(syncBar).observe(root, { attributes: true, attributeFilter: ["data-theme", "data-mode"] });
  } catch (e) { /* 오래된 브라우저: 처음 색만 */ }
})();
