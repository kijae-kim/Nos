// 지도 (추억 › 기록 지도, 장소 화면의 작은 지도). 국내는 카카오맵, 해외는 Leaflet + OpenStreetMap.
// 지도가 있는 화면에서만 실리고, 라이브러리·경계 파일은 필요할 때만 받는다.
// 카카오 키가 없거나 카카오맵을 5초 안에 못 불러오거나 그리다 실패하면 Leaflet 으로 그린다.
// 장소 고르기(place-picker.js)도 여기 불러오기 함수를 쓴다 (window.NosMap).
(function () {
  "use strict";

  var LIBS = {
    topojson: "https://cdn.jsdelivr.net/npm/topojson-client@3.1.0/dist/topojson-client.min.js",
    leafletCss: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.css",
    leaflet: "https://cdnjs.cloudflare.com/ajax/libs/leaflet/1.9.4/leaflet.js",
    clusterCss: "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/MarkerCluster.css",
    cluster: "https://cdnjs.cloudflare.com/ajax/libs/leaflet.markercluster/1.5.3/leaflet.markercluster.js",
  };
  var KOREA_ID = "410";
  // 해안선 단순화·섬 때문에 시·군·구 다각형 밖으로 잡히는 한국 장소를 국내로 두는 바다 영역
  var KOREA_SEA = { south: 32.8, north: 38.9, west: 124.0, east: 132.0 };
  var OSM_TILES = "https://tile.openstreetmap.org/{z}/{x}/{y}.png";

  // ---------- 불러오기 ----------
  function loadScript(src, referrerPolicy) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      // 사이트는 Referrer-Policy: same-origin 이라 바깥 요청에 주소를 안 보낸다.
      // 카카오맵은 등록 도메인을 Referer 로 확인하므로 카카오 스크립트에는 출처(도메인)만 보낸다.
      if (referrerPolicy) s.referrerPolicy = referrerPolicy;
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
      // 받기에 실패했을 때만 다음에 다시 받는다 (받는 중이거나 받은 것은 그대로 쓴다)
      leafletReady.catch(function () { leafletReady = null; });
    }
    return leafletReady;
  }
  var kakaoReady = null;
  function loadKakao(key) {
    if (!key) return Promise.reject(new Error("no key"));
    if (!kakaoReady) {
      var load = loadScript("https://dapi.kakao.com/v2/maps/sdk.js?appkey=" + encodeURIComponent(key) + "&autoload=false&libraries=clusterer", "strict-origin-when-cross-origin")
        .then(function () { return new Promise(function (resolve) { window.kakao.maps.load(resolve); }); });
      var timeout = new Promise(function (_, reject) { setTimeout(function () { reject(new Error("timeout")); }, 5000); });
      kakaoReady = Promise.race([load, timeout]);
      kakaoReady.catch(function () { kakaoReady = null; });
    }
    return kakaoReady;
  }
  function osmLayer(L) {
    return L.tileLayer(OSM_TILES, { maxZoom: 19, attribution: "© OpenStreetMap" });
  }
  window.NosMap = { loadScript: loadScript, getJSON: getJSON, loadLeaflet: loadLeaflet, loadKakao: loadKakao, osmLayer: osmLayer };

  // ---------- 국내/해외 판정 ----------
  function features(topo) {
    var key = Object.keys(topo.objects)[0];
    return window.topojson.feature(topo, topo.objects[key]).features.map(function (f) {
      f.bbox = bboxOf(f.geometry);
      return f;
    });
  }
  function polygonsOf(geometry) {
    return geometry.type === "Polygon" ? [geometry.coordinates] : geometry.type === "MultiPolygon" ? geometry.coordinates : [];
  }
  function bboxOf(geometry) {
    var b = [Infinity, Infinity, -Infinity, -Infinity];
    polygonsOf(geometry).forEach(function (poly) {
      poly[0].forEach(function (p) {
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
  function contains(f, lng, lat) {
    var b = f.bbox;
    if (lng < b[0] || lng > b[2] || lat < b[1] || lat > b[3]) return false;
    return polygonsOf(f.geometry).some(function (poly) {
      if (!inRing(lng, lat, poly[0])) return false;
      for (var h = 1; h < poly.length; h++) if (inRing(lng, lat, poly[h])) return false; // 구멍
      return true;
    });
  }
  function find(list, lng, lat) {
    for (var i = 0; i < list.length; i++) if (contains(list[i], lng, lat)) return list[i];
    return null;
  }
  function scopeOf(p, kr, world) {
    if (find(kr, p.lng, p.lat)) return "kr";
    var country = find(world, p.lng, p.lat);
    var inSea = p.lat >= KOREA_SEA.south && p.lat <= KOREA_SEA.north && p.lng >= KOREA_SEA.west && p.lng <= KOREA_SEA.east;
    return inSea && (!country || String(country.id) === KOREA_ID) ? "kr" : "world";
  }

  // ---------- 기록 지도 ----------
  function recordMap(root) {
    var canvas = root.querySelector("[data-map-canvas]");
    var cards = root.querySelector("[data-map-card]");
    var summary = root.querySelector("[data-map-summary]");
    var scopeBox = root.querySelector(".map-scope");
    var scopeButtons = Array.prototype.slice.call(root.querySelectorAll("[data-map-scope]"));
    var state = { scope: "kr", panes: {}, drawn: {}, groups: { kr: [], world: [] }, kakao: false };

    function showCards(list) {
      cards.innerHTML = "";
      list.forEach(function (p) {
        var a = document.createElement("a");
        a.className = "place-card card";
        a.href = p.url;
        var name = document.createElement("strong");
        name.textContent = p.name;
        var addr = document.createElement("small");
        addr.textContent = p.address || "";
        var count = document.createElement("span");
        count.className = "meta";
        count.textContent = "사진 " + p.photos + "장";
        a.appendChild(name); a.appendChild(addr); a.appendChild(count);
        cards.appendChild(a);
      });
      cards.hidden = !list.length;
    }
    function showSummary(scope) {
      var n = state.groups[scope].length;
      summary.textContent = n ? n + "곳" : (scope === "kr" ? "아직 기록한 국내 장소가 없어요." : "아직 기록한 해외 장소가 없어요.");
    }

    function drawLeaflet(pane, scope, focus) {
      var L = window.L;
      var map = L.map(pane, { zoomControl: true, worldCopyJump: true });
      osmLayer(L).addTo(map);
      var icon = L.divIcon({ className: "map-pin", iconSize: [18, 18] });
      var cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 50 });
      state.groups[scope].forEach(function (p) {
        var m = L.marker([p.lat, p.lng], { icon: icon, keyboard: true, title: p.name });
        m.place = p;
        m.on("click", function () { showCards([p]); });
        cluster.addLayer(m);
      });
      cluster.on("clusterclick", function (e) {
        showCards(e.layer.getAllChildMarkers().map(function (m) { return m.place; }));
      });
      map.addLayer(cluster);
      var view = {
        setFocus: function (lat, lng) { map.setView([lat, lng], 15); },
        resize: function () { map.invalidateSize(); },
      };
      view.refit = function () {
        fit(view, scope, focus, function (pts) { map.fitBounds(pts, { padding: [28, 28], maxZoom: 14 }); },
          function () { scope === "kr" ? map.setView([36.4, 127.8], 6) : map.setView([25, 10], 2); });
      };
      view.refit();
      return view;
    }

    function drawKakao(pane, scope, focus) {
      var kakao = window.kakao;
      var map = new kakao.maps.Map(pane, { center: new kakao.maps.LatLng(36.4, 127.8), level: 13 });
      map.addControl(new kakao.maps.ZoomControl(), kakao.maps.ControlPosition.RIGHT);
      var byMarker = [];
      var markers = state.groups[scope].map(function (p) {
        var m = new kakao.maps.Marker({ position: new kakao.maps.LatLng(p.lat, p.lng), title: p.name });
        byMarker.push({ marker: m, place: p });
        kakao.maps.event.addListener(m, "click", function () { showCards([p]); });
        return m;
      });
      var clusterer = new kakao.maps.MarkerClusterer({ map: map, averageCenter: true, minLevel: 6 });
      clusterer.addMarkers(markers);
      kakao.maps.event.addListener(clusterer, "clusterclick", function (c) {
        var inside = c.getMarkers();
        showCards(byMarker.filter(function (x) { return inside.indexOf(x.marker) !== -1; }).map(function (x) { return x.place; }));
      });
      var view = {
        setFocus: function (lat, lng) { map.setLevel(3); map.setCenter(new kakao.maps.LatLng(lat, lng)); },
        resize: function () { map.relayout(); },
      };
      view.refit = function () {
        fit(view, scope, focus, function (pts) {
          var b = new kakao.maps.LatLngBounds();
          pts.forEach(function (p) { b.extend(new kakao.maps.LatLng(p[0], p[1])); });
          map.setBounds(b, 28, 28, 28, 28);
          if (map.getLevel() < 4) map.setLevel(4);
        }, function () { map.setLevel(13); });
      };
      view.refit();
      return view;
    }

    function fit(view, scope, focus, fitPoints, fallback) {
      if (focus && focus.scope === scope) return view.setFocus(focus.lat, focus.lng);
      var pts = state.groups[scope].map(function (p) { return [p.lat, p.lng]; });
      if (pts.length) fitPoints(pts); else fallback();
    }

    function show(scope, focus) {
      state.scope = scope;
      scopeButtons.forEach(function (b, i) {
        var on = b.dataset.mapScope === scope;
        b.classList.toggle("on", on);
        if (on) scopeBox.querySelector(".thumb").style.transform = "translateX(" + i * 100 + "%)";
      });
      Object.keys(state.panes).forEach(function (k) { state.panes[k].hidden = k !== scope; });
      showCards([]);
      showSummary(scope);
      if (state.drawn[scope]) {
        state.drawn[scope].resize();
        if (focus && focus.scope === scope) state.drawn[scope].setFocus(focus.lat, focus.lng);
        return;
      }
      var pane = state.panes[scope];
      if (scope === "kr" && state.kakao) {
        try {
          state.drawn[scope] = drawKakao(pane, scope, focus);
          return;
        } catch (e) {
          state.kakao = false; // 카카오맵이 실렸어도 지도를 못 만들면(도메인 미등록 등) Leaflet 으로
          pane.innerHTML = "";
        }
      }
      state.drawn[scope] = drawLeaflet(pane, scope, focus);
    }

    function start() {
      ["kr", "world"].forEach(function (k) {
        var pane = document.createElement("div");
        pane.className = "map-pane";
        pane.hidden = true;
        canvas.appendChild(pane);
        state.panes[k] = pane;
      });
      var kakaoOk = loadKakao(root.dataset.kakaoKey).then(function () { return true; }, function () { return false; });
      Promise.all([
        getJSON(root.dataset.dataUrl),
        getJSON(root.dataset.geoKr),
        getJSON(root.dataset.geoWorld),
        loadScript(LIBS.topojson),
        loadLeaflet(),
        kakaoOk,
      ]).then(function (r) {
        state.kakao = r[5];
        var kr = features(r[1]), world = features(r[2]);
        r[0].places.forEach(function (p) { state.groups[scopeOf(p, kr, world)].push(p); });
        var focus = null;
        var raw = new URLSearchParams(location.search).get("focus");
        if (raw) {
          var parts = raw.split(",").map(Number);
          if (parts.length === 2 && !parts.some(isNaN)) focus = { lat: parts[0], lng: parts[1], scope: scopeOf({ lat: parts[0], lng: parts[1] }, kr, world) };
        }
        show(focus ? focus.scope : state.groups.kr.length || !state.groups.world.length ? "kr" : "world", focus);
      }).catch(function () {
        Object.keys(state.panes).forEach(function (k) { state.panes[k].remove(); });
        state.panes = {};
        summary.innerHTML = "";
        summary.appendChild(document.createTextNode("지도를 불러오지 못했어요. "));
        var retry = document.createElement("button");
        retry.type = "button"; retry.className = "link-btn"; retry.textContent = "다시 불러오기";
        retry.addEventListener("click", function () { summary.textContent = "지도를 불러오고 있어요…"; start(); });
        summary.appendChild(retry);
      });
    }

    scopeButtons.forEach(function (b) {
      b.addEventListener("click", function () { if (Object.keys(state.panes).length) show(b.dataset.mapScope); });
    });
    start();
  }

  // ---------- 장소 화면의 작은 지도 ----------
  function miniMap(box) {
    var lat = parseFloat(box.dataset.lat), lng = parseFloat(box.dataset.lng);
    if (isNaN(lat) || isNaN(lng)) return;
    // 한국 근처면 카카오맵, 아니면 바로 Leaflet
    var nearKorea = lat >= KOREA_SEA.south && lat <= KOREA_SEA.north && lng >= KOREA_SEA.west && lng <= KOREA_SEA.east;
    var leaflet = function () {
      return loadLeaflet().then(function () {
        var L = window.L;
        var map = L.map(box, { scrollWheelZoom: false, zoomControl: true }).setView([lat, lng], 15);
        osmLayer(L).addTo(map);
        L.marker([lat, lng], { icon: L.divIcon({ className: "map-pin", iconSize: [18, 18] }) }).addTo(map);
      });
    };
    var kakao = nearKorea ? loadKakao(box.dataset.kakaoKey) : Promise.reject(new Error("abroad"));
    kakao.then(function () {
      try {
        var k = window.kakao;
        var center = new k.maps.LatLng(lat, lng);
        var map = new k.maps.Map(box, { center: center, level: 3 });
        map.setZoomable(false);
        new k.maps.Marker({ map: map, position: center });
      } catch (e) {
        box.innerHTML = "";
        return leaflet();
      }
    }, leaflet).catch(function () { box.hidden = true; });
  }

  var record = document.querySelector("[data-record-map]");
  if (record) recordMap(record);
  Array.prototype.forEach.call(document.querySelectorAll("[data-mini-map]"), miniMap);
})();
