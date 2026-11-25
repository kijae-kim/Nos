// 캘린더 태그 모아 보기: 태그를 누르면 화면 전체를 다시 불러오지 않고, 태그 줄·목록과 달력 막대의 흐림만 바꾼다.
// (전체를 다시 불러오면 화면이 잠깐 비고 처음 위치로 튀어 버벅여 보였다.) 달이 바뀌어야 하면 그냥 그 주소로 간다.
(function () {
  "use strict";
  var zones = function (doc) { return Array.prototype.slice.call(doc.querySelectorAll("[data-label-zone]")); };
  if (!zones(document).length || !window.fetch || !window.DOMParser) return;
  var seq = 0;

  function sameMonth(doc) {
    var a = document.querySelector(".page-title"), b = doc.querySelector(".page-title");
    return a && b && a.textContent.trim() === b.textContent.trim() &&
      document.querySelectorAll(".piece").length === doc.querySelectorAll(".piece").length;
  }
  function apply(doc) {
    var next = zones(doc);
    zones(document).forEach(function (zone, i) { if (next[i]) zone.innerHTML = next[i].innerHTML; });
    // 달력 막대: 고른 태그가 아닌 일정은 흐리게 (같은 달이라 막대 순서가 같다)
    var fresh = doc.querySelectorAll(".piece");
    document.querySelectorAll(".piece").forEach(function (p, i) {
      if (fresh[i]) p.classList.toggle("dim", fresh[i].classList.contains("dim"));
    });
  }
  function load(url, push) {
    var mine = ++seq;
    document.documentElement.classList.add("label-loading");
    fetch(url, { credentials: "same-origin" })
      .then(function (r) {
        if (!r.ok || r.redirected) throw new Error(r.status);
        return r.text();
      })
      .then(function (html) {
        if (mine !== seq) return;
        var doc = new DOMParser().parseFromString(html, "text/html");
        if (!sameMonth(doc)) { location.href = url; return; }
        apply(doc);
        if (push) history.pushState({ labels: true }, "", url);
        document.documentElement.classList.remove("label-loading");
      })
      .catch(function () { location.href = url; }); // 안 되면 예전처럼 그 주소로
  }

  document.addEventListener("click", function (e) {
    if (e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey) return;
    var a = e.target.closest && e.target.closest("a.label-chip:not(.manage), [data-label-zone] .list-head .add-link");
    if (!a) return;
    var url = new URL(a.href, location.href);
    if (url.pathname !== location.pathname) return; // 다른 화면으로 가는 링크는 그대로
    e.preventDefault();
    // 누른 칩은 바로 눌린 모양으로 (응답을 기다리지 않고)
    document.querySelectorAll("a.label-chip.on").forEach(function (c) { c.classList.remove("on"); });
    if (a.classList.contains("label-chip")) a.classList.add("on");
    load(url.href, true);
  }, true); // 먼저 받아(캡처) 막아야 화면 이동 때 뜨는 '불러오는 중' 덮개(app.js)가 뜨지 않는다
  window.addEventListener("popstate", function () { load(location.href, false); });
})();
