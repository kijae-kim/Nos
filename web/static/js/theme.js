// 화면이 그려지기 전에 팔레트(배/여정)와 화면 모드(라이트/다크)를 정한다.
// 저장된 값이 없으면 기본 팔레트는 배, 화면 모드는 기기 설정을 따른다. 시작 화면을 보여 줄지도 여기서 정한다.
(function () {
  var root = document.documentElement;
  var palette = "boat";
  var mode = window.matchMedia("(prefers-color-scheme: dark)").matches ? "dark" : "light";
  try {
    var savedPalette = localStorage.getItem("palette");
    var savedMode = localStorage.getItem("mode");
    if (savedPalette === "boat" || savedPalette === "journey") palette = savedPalette;
    if (savedMode === "light" || savedMode === "dark") mode = savedMode;
  } catch (e) {}
  root.dataset.theme = palette;
  root.dataset.mode = mode;
  // 이 탭(또는 설치한 앱)을 처음 열었을 때만 시작 화면을 보여 준다
  try {
    if (!sessionStorage.getItem("splashed")) root.classList.add("splash-on");
  } catch (e) {}
})();
