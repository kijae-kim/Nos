// 다녀온 곳 색칠 지도 (추억 › 기록 › 색칠 지도). 실제 지도 없이 경계만 SVG 로 그린다.
// 단계: 전국(시·군·구) → 서울(구) → 구(동). 칠함 = 직접 칠함, 또는 (직접 지우지 않았고 장소·사진이 그 안에 있음).
// 지역 판정 함수는 map.js 의 window.NosMap.geo 를 쓴다.
(function () {
  "use strict";
  var root = document.querySelector("[data-coloring-map]");
  if (!root || !window.NosMap) return;
  var M = window.NosMap, G = M.geo;

  var SIDO = { 11: "서울", 21: "부산", 22: "대구", 23: "인천", 24: "광주", 25: "대전", 26: "울산", 29: "세종", 31: "경기", 32: "강원", 33: "충북", 34: "충남", 35: "전북", 36: "전남", 37: "경북", 38: "경남", 39: "제주" };
  var SVG_NS = "http://www.w3.org/2000/svg";
  var W = 1000; // viewBox 너비

  var svg = root.querySelector("[data-color-svg]");
  var crumbs = root.querySelector("[data-crumbs]");
  var summary = root.querySelector("[data-color-summary]");
  var note = root.querySelector("[data-color-note]");
  var panel = root.querySelector("[data-region-panel]");

  var data = null; // { kr, dongs, counts: {sigungu:{}, dong:{}}, marks: {} , dongGu: {} }
  var stage = { name: "nation", gu: null };
  var selected = null; // { level, code }
  var cache = {}; // 단계별 투영·경로

  // ---------- 계산 ----------
  function sido(code) { return SIDO[String(code).slice(0, 2)] || ""; }
  function isSeoul(code) { return String(code).slice(0, 2) === "11"; }
  function key(level, code) { return level + ":" + code; }
  function count(level, code) { return data.counts[level][code] || { place: 0, photo: 0 }; }
  function colored(level, code) {
    var mark = data.marks[key(level, code)];
    if (mark === "on") return true;
    if (mark === "off") return false;
    var c = count(level, code);
    if (c.place + c.photo > 0) return true;
    // 서울 구: 그 안의 동이 하나라도 칠해지면 구도 칠한다
    if (level === "sigungu" && isSeoul(code)) {
      return data.dongs.some(function (d) { return data.dongGu[d.properties.code] === code && colored("dong", d.properties.code); });
    }
    return false;
  }
  function regionName(level, f) {
    if (level === "dong") {
      var gu = byCode(data.kr, data.dongGu[f.properties.code]);
      return (gu ? gu.properties.name + " " : "") + f.properties.name;
    }
    return (sido(f.properties.code) + " " + f.properties.name).trim();
  }
  function byCode(list, code) {
    for (var i = 0; i < list.length; i++) if (String(list[i].properties.code) === String(code)) return list[i];
    return null;
  }
  // 대표점: 가장 큰 바깥 고리의 평균점
  function centerOf(f) {
    var best = null;
    G.polygonsOf(f.geometry).forEach(function (poly) { if (!best || poly[0].length > best.length) best = poly[0]; });
    var x = 0, y = 0;
    best.forEach(function (p) { x += p[0]; y += p[1]; });
    return [x / best.length, y / best.length];
  }

  function prepare(res) {
    var kr = G.features(res[1]), dongs = G.features(res[2]);
    var seoulGu = kr.filter(function (f) { return isSeoul(f.properties.code); });
    var dongGu = {};
    dongs.forEach(function (d) {
      var c = centerOf(d);
      var gu = G.find(seoulGu, c[0], c[1]);
      if (gu) dongGu[d.properties.code] = String(gu.properties.code);
    });
    var counts = { sigungu: {}, dong: {} };
    var add = function (level, code, kind) {
      var c = counts[level][code] || (counts[level][code] = { place: 0, photo: 0 });
      c[kind] += 1;
    };
    res[0].points.forEach(function (p) {
      var s = G.find(kr, p.lng, p.lat);
      if (!s) return; // 해외·바다
      add("sigungu", String(s.properties.code), p.kind);
      if (isSeoul(s.properties.code)) {
        var d = G.find(dongs, p.lng, p.lat);
        if (d) add("dong", String(d.properties.code), p.kind);
      }
    });
    var marks = {};
    res[0].marks.forEach(function (m) { marks[key(m.level, m.code)] = m.state; });
    data = { kr: kr, dongs: dongs, dongGu: dongGu, counts: counts, marks: marks };
  }

  // ---------- 그리기 ----------
  function stageRegions() {
    if (stage.name === "nation") return { level: "sigungu", list: data.kr };
    if (stage.name === "seoul") return { level: "sigungu", list: data.kr.filter(function (f) { return isSeoul(f.properties.code); }) };
    return { level: "dong", list: data.dongs.filter(function (d) { return data.dongGu[d.properties.code] === stage.gu; }) };
  }
  function project(list) {
    var b = [Infinity, Infinity, -Infinity, -Infinity];
    list.forEach(function (f) {
      b[0] = Math.min(b[0], f.bbox[0]); b[1] = Math.min(b[1], f.bbox[1]);
      b[2] = Math.max(b[2], f.bbox[2]); b[3] = Math.max(b[3], f.bbox[3]);
    });
    var k = Math.cos(((b[1] + b[3]) / 2) * Math.PI / 180); // 위도에 따라 경도 폭을 줄인다
    var scale = W / ((b[2] - b[0]) * k);
    var height = Math.round((b[3] - b[1]) * scale);
    return {
      height: height,
      xy: function (lng, lat) { return [((lng - b[0]) * k * scale), ((b[3] - lat) * scale)]; },
    };
  }
  function pathOf(f, pr) {
    var d = "";
    G.polygonsOf(f.geometry).forEach(function (poly) {
      poly.forEach(function (ring) {
        ring.forEach(function (p, i) {
          var q = pr.xy(p[0], p[1]);
          d += (i ? "L" : "M") + q[0].toFixed(1) + " " + q[1].toFixed(1);
        });
        d += "Z";
      });
    });
    return d;
  }
  function build() {
    var id = stage.name === "gu" ? "gu:" + stage.gu : stage.name;
    if (cache[id]) return cache[id];
    var r = stageRegions(), pr = project(r.list);
    cache[id] = {
      level: r.level, height: pr.height,
      items: r.list.map(function (f) {
        var c = centerOf(f);
        return { f: f, code: String(f.properties.code), d: pathOf(f, pr), label: pr.xy(c[0], c[1]) };
      }),
    };
    return cache[id];
  }
  function el(name, attrs) {
    var e = document.createElementNS(SVG_NS, name);
    Object.keys(attrs).forEach(function (k) { e.setAttribute(k, attrs[k]); });
    return e;
  }
  function draw() {
    var view = build();
    svg.setAttribute("viewBox", "0 0 " + W + " " + view.height);
    svg.innerHTML = "";
    var shapes = el("g", {}), labels = el("g", { "class": "region-labels" });
    // 글자는 화면에서 같은 크기로 보이게 viewBox 비율로 키운다
    var px = (svg.clientWidth || 340);
    var fontSize = (stage.name === "nation" ? 9 : 11) * W / px;
    labels.setAttribute("font-size", fontSize.toFixed(1));
    view.items.forEach(function (it) {
      var on = colored(view.level, it.code);
      var sel = selected && selected.level === view.level && selected.code === it.code;
      var p = el("path", { d: it.d, "class": "region" + (on ? " on" : "") + (sel ? " sel" : ""), "data-code": it.code, tabindex: "0", role: "button" });
      p.setAttribute("aria-label", regionName(view.level, it.f) + (on ? " 칠함" : ""));
      shapes.appendChild(p);
      // 전국은 칠해진 곳만 이름, 서울·구는 모두
      if (stage.name !== "nation" || on) {
        var t = el("text", { x: it.label[0].toFixed(1), y: it.label[1].toFixed(1) });
        t.textContent = it.f.properties.name;
        labels.appendChild(t);
      }
    });
    // 고른 지역은 위에 다시 그려 테두리가 가려지지 않게
    var selPath = shapes.querySelector(".sel");
    if (selPath) shapes.appendChild(selPath);
    svg.appendChild(shapes);
    svg.appendChild(labels);
    drawCrumbs();
    drawSummary();
    note.hidden = stage.name === "nation";
  }
  function drawCrumbs() {
    crumbs.innerHTML = "";
    var add = function (text, go) {
      if (crumbs.childNodes.length) crumbs.appendChild(document.createTextNode(" › "));
      var b = document.createElement(go ? "button" : "span");
      b.textContent = text;
      if (go) { b.type = "button"; b.className = "link-btn"; b.addEventListener("click", go); }
      crumbs.appendChild(b);
    };
    add("전국", stage.name === "nation" ? null : function () { goto("nation"); });
    if (stage.name !== "nation") add("서울", stage.name === "seoul" ? null : function () { goto("seoul"); });
    if (stage.name === "gu") add(byCode(data.kr, stage.gu).properties.name, null);
  }
  function drawSummary() {
    var n = function (level, list) { return list.filter(function (f) { return colored(level, String(f.properties.code)); }).length; };
    if (stage.name === "nation") {
      summary.textContent = "시·군·구 " + n("sigungu", data.kr) + "/" + data.kr.length;
    } else if (stage.name === "seoul") {
      var gus = data.kr.filter(function (f) { return isSeoul(f.properties.code); });
      summary.textContent = "구 " + n("sigungu", gus) + "/" + gus.length + " · 동 " + n("dong", data.dongs) + "/" + data.dongs.length;
    } else {
      var ds = stageRegions().list;
      summary.textContent = "동 " + n("dong", ds) + "/" + ds.length;
    }
  }

  // ---------- 아래 지역 칸 ----------
  function showPanel() {
    panel.innerHTML = "";
    if (!selected) { panel.hidden = true; return; }
    var list = selected.level === "dong" ? data.dongs : data.kr;
    var f = byCode(list, selected.code);
    var c = count(selected.level, selected.code);
    var mark = data.marks[key(selected.level, selected.code)] || "auto";
    var title = document.createElement("strong");
    title.textContent = regionName(selected.level, f);
    var why = document.createElement("small");
    why.textContent = c.place + c.photo ? "장소 " + c.place + "곳 · 사진 " + c.photo + "장" : "기록 없음";
    var buttons = document.createElement("div");
    buttons.className = "chips region-actions";
    [["on", "칠하기"], ["off", "지우기"], ["auto", "자동으로"]].forEach(function (pair) {
      var b = document.createElement("button");
      b.type = "button";
      b.className = "chip-btn" + (mark === pair[0] ? " on" : "");
      b.setAttribute("aria-pressed", mark === pair[0] ? "true" : "false");
      b.textContent = pair[1];
      b.addEventListener("click", function () { setMark(selected.level, selected.code, pair[0]); });
      buttons.appendChild(b);
    });
    panel.appendChild(title); panel.appendChild(why); panel.appendChild(buttons);
    if (selected.level === "sigungu" && isSeoul(selected.code) && stage.name === "seoul") {
      var deeper = document.createElement("button");
      deeper.type = "button"; deeper.className = "btn"; deeper.textContent = "동까지 보기";
      var gu = selected.code;
      deeper.addEventListener("click", function () { goto("gu", gu); });
      panel.appendChild(deeper);
    }
    var msg = document.createElement("p");
    msg.className = "hint"; msg.setAttribute("data-panel-msg", ""); msg.hidden = true;
    panel.appendChild(msg);
    panel.hidden = false;
  }
  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  function setMark(level, code, state) {
    var k = key(level, code), before = data.marks[k];
    if (state === "auto") delete data.marks[k]; else data.marks[k] = state;
    draw(); showPanel(); // 저장 전에 바로 보여 준다
    fetch(root.dataset.markUrl, {
      method: "POST", credentials: "same-origin",
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ level: level, code: code, state: state }),
    }).then(function (r) { if (!r.ok) throw new Error("HTTP " + r.status); }).catch(function () {
      if (before === undefined) delete data.marks[k]; else data.marks[k] = before;
      draw(); showPanel();
      var m = panel.querySelector("[data-panel-msg]");
      if (m) { m.textContent = "저장하지 못했어요. 잠시 뒤 다시 해 볼까요?"; m.hidden = false; }
    });
  }

  function goto(name, gu) {
    stage = { name: name, gu: gu || null };
    selected = null;
    showPanel();
    draw();
  }

  svg.addEventListener("click", function (e) {
    var p = e.target.closest("path[data-code]");
    if (!p) return;
    var code = p.getAttribute("data-code");
    if (stage.name === "nation" && isSeoul(code)) return goto("seoul"); // 서울은 작아서 통째로 들어간다
    selected = { level: stage.name === "gu" ? "dong" : "sigungu", code: code };
    draw(); showPanel();
  });
  svg.addEventListener("keydown", function (e) {
    if ((e.key === "Enter" || e.key === " ") && e.target.matches("path[data-code]")) { e.preventDefault(); e.target.dispatchEvent(new MouseEvent("click", { bubbles: true })); }
  });

  // ---------- 처음 열기 ----------
  var started = false;
  function start() {
    if (started) return;
    started = true;
    summary.textContent = "지도를 불러오고 있어요…";
    Promise.all([
      M.getJSON(root.dataset.dataUrl),
      M.getJSON(root.dataset.geoKr),
      M.getJSON(root.dataset.geoSeoul),
      window.topojson ? Promise.resolve() : M.loadScript(G.topojsonUrl),
    ]).then(function (res) {
      prepare(res);
      draw();
    }).catch(function () {
      started = false;
      summary.textContent = "지도를 불러오지 못했어요. 색칠 지도를 다시 눌러 주세요.";
    });
  }

  // ---------- 핀 지도 · 색칠 지도 전환 ----------
  var pinBox = document.querySelector("[data-record-map]");
  var toggles = Array.prototype.slice.call(document.querySelectorAll("[data-record-view]"));
  function setView(view) {
    toggles.forEach(function (b, i) {
      var on = b.dataset.recordView === view;
      b.classList.toggle("on", on);
      b.setAttribute("aria-pressed", on ? "true" : "false");
      var thumb = b.parentElement.querySelector(".thumb");
      if (on && thumb) thumb.style.transform = "translateX(" + i * 100 + "%)";
    });
    root.hidden = view !== "color";
    if (pinBox) pinBox.hidden = view !== "pin";
    try { localStorage.setItem("nos.recordView", view); } catch (e) { /* 저장 못 해도 괜찮다 */ }
    document.dispatchEvent(new CustomEvent("nos:record-view", { detail: view }));
    if (view === "color") { start(); if (data) draw(); }
  }
  toggles.forEach(function (b) { b.addEventListener("click", function () { setView(b.dataset.recordView); }); });
  var saved = null;
  try { saved = localStorage.getItem("nos.recordView"); } catch (e) { /* 없음 */ }
  if (saved === "color") setView("color");
})();
