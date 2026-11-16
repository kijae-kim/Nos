// 사진 지도 (앨범 › 지도). 국내는 카카오맵, 해외는 Leaflet + OpenStreetMap.
// 지도 칸을 처음 열 때만 데이터·라이브러리·경계 파일을 불러온다 (앨범 첫 화면을 느리게 하지 않게).
// 카카오 키가 없거나 카카오맵을 5초 안에 못 불러오면 국내도 Leaflet 으로 그린다.
(function () {
  "use strict";
  var root = document.querySelector("[data-photo-map]");
  if (!root) return;

  var LIBS = {
    topojson: "https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js",
    leafletCss: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css",
    leaflet: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js",
    clusterCss: "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.css",
    cluster: "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/leaflet.markercluster.js",
  };
  // 시·군·구 코드 앞 두 자리 → 시·도 (KOSTAT 2018)
  var SIDO = { 11: "서울", 21: "부산", 22: "대구", 23: "인천", 24: "광주", 25: "대전", 26: "울산", 29: "세종", 31: "경기", 32: "강원", 33: "충북", 34: "충남", 35: "전북", 36: "전남", 37: "경북", 38: "경남", 39: "제주" };
  var KOREA_ID = "410";
  // 해안선 단순화·섬·독도 때문에 시·군·구 다각형 밖으로 잡히는 한국 사진을 국내로 두는 바다 영역
  var KOREA_SEA = { south: 32.8, north: 38.9, west: 124.0, east: 132.0 };

  var canvas = root.querySelector("[data-map-canvas]");
  var strip = root.querySelector("[data-map-strip]");
  var summary = root.querySelector("[data-map-summary]");
  var empty = root.querySelector("[data-map-empty]");
  var scopeBox = root.querySelector(".map-scope");
  var scopeButtons = Array.prototype.slice.call(root.querySelectorAll("[data-map-scope]"));
  var started = false;
  var state = { scope: "kr", panes: {}, drawn: {}, groups: { kr: [], world: [] }, regions: { kr: {}, world: {} } };

  // ---------- 불러오기 ----------
  function loadScript(src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src; s.async = true;
      s.onload = resolve; s.onerror = reject;
      document.head.appendChild(s);
    });
  }
  function loadCss(href) {
    var l = document.createElement("link");
    l.rel = "stylesheet"; l.href = href;
    document.head.appendChild(l);
  }
  function getJSON(url) {
    return fetch(url, { credentials: "same-origin" }).then(function (r) {
      if (!r.ok) throw new Error("HTTP " + r.status);
      return r.json();
    });
  }
  var leafletReady = null;
  function loadLeaflet() {
    if (!leafletReady) {
      loadCss(LIBS.leafletCss);
      loadCss(LIBS.clusterCss);
      leafletReady = loadScript(LIBS.leaflet).then(function () { return loadScript(LIBS.cluster); });
    }
    return leafletReady;
  }
  function loadKakao(key) {
    if (!key) return Promise.reject(new Error("no key"));
    var load = loadScript("https://dapi.kakao.com/v2/maps/sdk.js?appkey=" + encodeURIComponent(key) + "&autoload=false&libraries=clusterer")
      .then(function () { return new Promise(function (resolve) { window.kakao.maps.load(resolve); }); });
    var timeout = new Promise(function (_, reject) { setTimeout(function () { reject(new Error("timeout")); }, 5000); });
    return Promise.race([load, timeout]);
  }

  // ---------- 지역 판정 ----------
  function features(topo) {
    var key = Object.keys(topo.objects)[0];
    return window.topojson.feature(topo, topo.objects[key]).features.map(function (f) {
      f.bbox = bboxOf(f.geometry);
      return f;
    });
  }
  function eachRing(geometry, fn) {
    var polys = geometry.type === "Polygon" ? [geometry.coordinates] : geometry.type === "MultiPolygon" ? geometry.coordinates : [];
    polys.forEach(function (poly) { poly.forEach(function (ring, i) { fn(ring, i === 0, poly); }); });
  }
  function bboxOf(geometry) {
    var b = [Infinity, Infinity, -Infinity, -Infinity];
    eachRing(geometry, function (ring) {
      ring.forEach(function (p) {
        if (p[0] < b[0]) b[0] = p[0]; if (p[1] < b[1]) b[1] = p[1];
        if (p[0] > b[2]) b[2] = p[0]; if (p[1] > b[3]) b[3] = p[1];
      });
    });
    return b;
  }
  function inRing(x, y, ring) {
    var inside = false;
    for (var i = 0, j = ring.length - 1; i < ring.length; j = i++) {
      var xi = ring[i][0], yi = ring[i][1], xj = ring[j][0], yj = ring[j][1];
      if ((yi > y) !== (yj > y) && x < (xj - xi) * (y - yi) / (yj - yi) + xi) inside = !inside;
    }
    return inside;
  }
  function contains(feature, lng, lat) {
    var b = feature.bbox;
    if (lng < b[0] || lng > b[2] || lat < b[1] || lat > b[3]) return false;
    var polys = feature.geometry.type === "Polygon" ? [feature.geometry.coordinates] : feature.geometry.coordinates;
    return polys.some(function (poly) {
      if (!inRing(lng, lat, poly[0])) return false;
      for (var h = 1; h < poly.length; h++) if (inRing(lng, lat, poly[h])) return false; // 구멍
      return true;
    });
  }
  function find(list, lng, lat) {
    for (var i = 0; i < list.length; i++) if (contains(list[i], lng, lat)) return list[i];
    return null;
  }
  // 사진 하나를 국내/해외와 지역(색칠 대상)으로 나눈다
  function classify(p, kr, world) {
    var district = find(kr, p.lng, p.lat);
    if (district) return { scope: "kr", region: district };
    var country = find(world, p.lng, p.lat);
    var inSea = p.lat >= KOREA_SEA.south && p.lat <= KOREA_SEA.north && p.lng >= KOREA_SEA.west && p.lng <= KOREA_SEA.east;
    if (inSea && (!country || String(country.id) === KOREA_ID)) return { scope: "kr", region: null };
    return { scope: "world", region: country };
  }
  function regionName(scope, f) {
    if (scope === "kr") {
      var sido = SIDO[String(f.properties.code).slice(0, 2)];
      return (sido ? sido + " " : "") + f.properties.name;
    }
    return f.properties.name;
  }
  // 사진 수에 따라 색 진하기
  // 확대해서 색칠한 지역 안을 볼 때도 길과 이름이 읽히도록 옅게 둔다
  function opacity(n) { return n >= 10 ? 0.48 : n >= 5 ? 0.38 : n >= 2 ? 0.28 : 0.18; }
  function token(name, fallback) {
    var v = getComputedStyle(document.documentElement).getPropertyValue(name).trim();
    return v || fallback;
  }

  // ---------- 사진 줄 ----------
  function showStrip(photos) {
    strip.innerHTML = "";
    photos.slice().sort(function (a, b) { return a.taken < b.taken ? -1 : 1; }).forEach(function (p) {
      var a = document.createElement("a");
      a.href = p.url;
      a.setAttribute("aria-label", p.taken + " 사진 보기");
      var img = document.createElement("img");
      img.loading = "lazy"; img.decoding = "async"; img.alt = ""; img.src = p.src;
      a.appendChild(img);
      strip.appendChild(a);
    });
    strip.hidden = !photos.length;
  }

  // ---------- 요약 ----------
  function showSummary(scope) {
    var photos = state.groups[scope];
    var count = Object.keys(state.regions[scope]).length;
    if (!photos.length) {
      summary.textContent = scope === "kr" ? "아직 국내에서 찍은 사진이 없어요." : "아직 해외에서 찍은 사진이 없어요.";
    } else {
      summary.textContent = (scope === "kr" ? count + "곳" : count + "개 나라") + " · 사진 " + photos.length + "장";
    }
  }

  // ---------- Leaflet ----------
  function drawLeaflet(pane, scope, focus) {
    var L = window.L;
    var map = L.map(pane, { zoomControl: true, worldCopyJump: true });
    L.tileLayer("https://tile.openstreetmap.org/{z}/{x}/{y}.png", {
      maxZoom: 18, attribution: "© OpenStreetMap",
    }).addTo(map);
    var fill = token("--map-fill", "#4f6bff"), line = token("--map-line", "#4f6bff");
    var regions = state.regions[scope];
    Object.keys(regions).forEach(function (key) {
      var r = regions[key];
      L.geoJSON(r.feature, {
        style: { color: line, weight: 1, opacity: 0.7, fillColor: fill, fillOpacity: opacity(r.photos.length) },
      }).bindPopup(regionName(scope, r.feature) + " · 사진 " + r.photos.length + "장").addTo(map);
    });
    var cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 50 });
    var icon = L.divIcon({ className: "map-pin", iconSize: [18, 18] });
    state.groups[scope].forEach(function (p) {
      var m = L.marker([p.lat, p.lng], { icon: icon, keyboard: true, title: p.taken });
      m.photo = p;
      m.on("click", function () { showStrip([p]); });
      cluster.addLayer(m);
    });
    cluster.on("clusterclick", function (e) {
      showStrip(e.layer.getAllChildMarkers().map(function (m) { return m.photo; }));
    });
    map.addLayer(cluster);
    var view = { setFocus: function (lat, lng) { map.setView([lat, lng], 15); }, resize: function () { map.invalidateSize(); } };
    fit(view, scope, focus, function (bounds) { map.fitBounds(bounds, { padding: [24, 24], maxZoom: 13 }); },
      function () { scope === "kr" ? map.setView([36.4, 127.8], 6) : map.setView([25, 10], 2); });
    return view;
  }

  // ---------- 카카오맵 ----------
  function drawKakao(pane, scope, focus) {
    var kakao = window.kakao;
    var map = new kakao.maps.Map(pane, { center: new kakao.maps.LatLng(36.4, 127.8), level: 13 });
    map.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT);
    var fill = token("--map-fill", "#4f6bff"), line = token("--map-line", "#4f6bff");
    var info = new kakao.maps.InfoWindow({ removable: true });
    var regions = state.regions[scope];
    Object.keys(regions).forEach(function (key) {
      var r = regions[key];
      var paths = [];
      eachRing(r.feature.geometry, function (ring) {
        paths.push(ring.map(function (c) { return new kakao.maps.LatLng(c[1], c[0]); }));
      });
      var polygon = new kakao.maps.Polygon({
        map: map, path: paths, strokeWeight: 1, strokeColor: line, strokeOpacity: 0.7,
        fillColor: fill, fillOpacity: opacity(r.photos.length),
      });
      kakao.maps.event.addListener(polygon, "click", function (e) {
        info.setContent('<div class="map-info">' + regionName(scope, r.feature) + " · 사진 " + r.photos.length + "장</div>");
        info.setPosition(e.latLng);
        info.open(map);
      });
    });
    var byMarker = [];
    var markers = state.groups[scope].map(function (p) {
      var m = new kakao.maps.Marker({ position: new kakao.maps.LatLng(p.lat, p.lng), title: p.taken });
      byMarker.push({ marker: m, photo: p });
      kakao.maps.event.addListener(m, "click", function () { showStrip([p]); });
      return m;
    });
    var clusterer = new kakao.maps.MarkerClusterer({ map: map, averageCenter: true, minLevel: 6, disableClickZoom: false });
    clusterer.addMarkers(markers);
    kakao.maps.event.addListener(clusterer, "clusterclick", function (cluster) {
      var inside = cluster.getMarkers();
      showStrip(byMarker.filter(function (x) { return inside.indexOf(x.marker) !== -1; }).map(function (x) { return x.photo; }));
    });
    var view = {
      setFocus: function (lat, lng) { map.setLevel(3); map.setCenter(new kakao.maps.LatLng(lat, lng)); },
      resize: function () { map.relayout(); },
    };
    fit(view, scope, focus, function (pts) {
      var b = new kakao.maps.LatLngBounds();
      pts.forEach(function (p) { b.extend(new kakao.maps.LatLng(p[0], p[1])); });
      map.setBounds(b, 24, 24, 24, 24);
      if (map.getLevel() < 5) map.setLevel(5);
    }, function () { map.setLevel(13); });
    return view;
  }

  // 처음 보일 자리: focus 가 있으면 그곳, 아니면 사진 전체가 보이게
  function fit(view, scope, focus, fitPoints, fallback) {
    if (focus && focus.scope === scope) return view.setFocus(focus.lat, focus.lng);
    var pts = state.groups[scope].map(function (p) { return [p.lat, p.lng]; });
    if (pts.length) fitPoints(pts); else fallback();
  }

  // ---------- 국내/해외 전환 ----------
  function show(scope, focus) {
    state.scope = scope;
    scopeButtons.forEach(function (b, i) {
      var on = b.dataset.mapScope === scope;
      b.classList.toggle("on", on);
      if (on) scopeBox.querySelector(".thumb").style.transform = "translateX(" + i * 100 + "%)";
    });
    Object.keys(state.panes).forEach(function (k) { state.panes[k].hidden = k !== scope; });
    showStrip([]);
    showSummary(scope);
    if (!state.drawn[scope]) {
      var pane = state.panes[scope];
      if (scope === "kr" && state.kakao) {
        try {
          state.drawn[scope] = drawKakao(pane, scope, focus);
        } catch (e) {
          // 카카오맵이 실렸어도 지도를 못 만들면(도메인 미등록 등) Leaflet 으로
          state.kakao = false;
          pane.innerHTML = "";
          state.drawn[scope] = drawLeaflet(pane, scope, focus);
        }
      } else {
        state.drawn[scope] = drawLeaflet(pane, scope, focus);
      }
    } else {
      state.drawn[scope].resize();
      if (focus && focus.scope === scope) state.drawn[scope].setFocus(focus.lat, focus.lng);
    }
  }

  function parseFocus(kr, world) {
    var raw = new URLSearchParams(location.search).get("focus");
    if (!raw) return null;
    var parts = raw.split(",").map(Number);
    if (parts.length !== 2 || parts.some(isNaN)) return null;
    var c = classify({ lat: parts[0], lng: parts[1] }, kr, world);
    return { lat: parts[0], lng: parts[1], scope: c.scope };
  }

  function start() {
    if (started) return;
    started = true;
    ["kr", "world"].forEach(function (k) {
      var pane = document.createElement("div");
      pane.className = "map-pane";
      pane.hidden = true;
      canvas.appendChild(pane);
      state.panes[k] = pane;
    });
    var kakaoReady = loadKakao(root.dataset.kakaoKey).then(function () { return true; }, function () { return false; });
    Promise.all([
      getJSON(root.dataset.dataUrl),
      getJSON(root.dataset.geoKr),
      getJSON(root.dataset.geoWorld),
      loadScript(LIBS.topojson),
      loadLeaflet(),
      kakaoReady,
    ]).then(function (r) {
      state.kakao = r[5];
      var photos = r[0].photos;
      if (!photos.length) {
        scopeBox.hidden = true; canvas.hidden = true; summary.hidden = true;
        empty.hidden = false;
        return;
      }
      var kr = features(r[1]), world = features(r[2]);
      photos.forEach(function (p) {
        var c = classify(p, kr, world);
        state.groups[c.scope].push(p);
        if (c.region) {
          var key = String(c.region.id || c.region.properties.code);
          var bucket = state.regions[c.scope][key] || (state.regions[c.scope][key] = { feature: c.region, photos: [] });
          bucket.photos.push(p);
        }
      });
      var focus = parseFocus(kr, world);
      var first = focus ? focus.scope : state.groups.kr.length ? "kr" : "world";
      show(first, focus);
    }).catch(function () {
      summary.textContent = "지도를 불러오지 못했어요. 잠시 뒤 다시 열어 볼까요?";
    });
  }

  scopeButtons.forEach(function (b) {
    b.addEventListener("click", function () { if (started) show(b.dataset.mapScope); });
  });
  var tab = document.querySelector('[data-target="album-map"]');
  if (tab) tab.addEventListener("click", function () {
    start();
    // 숨어 있던 칸이 보이게 된 뒤 지도 크기를 다시 잰다
    setTimeout(function () { if (state.drawn[state.scope]) state.drawn[state.scope].resize(); }, 50);
  });
  if (root.classList.contains("on")) start();
})();
