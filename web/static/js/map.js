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
  // 사진 핀: 작은 사진 동그라미. 서명 주소(?…&X-Amz-Signature=…)를 바꾸지 않도록 DOM 으로 만든다
  // (문자열 HTML 에 넣으며 & 를 바꾸면 R2 가 서명을 못 읽어 사진이 안 뜬다). 작은 사진이 없으면 카메라 아이콘.
  function photoPinEl(p) {
    var span = document.createElement("span");
    span.className = "photo-pin";
    if (p.thumb) {
      var safe = String(p.thumb).replace(/["\\\n]/g, function (c) { return "\\" + c; }); // CSS 문자열 안에서만 이스케이프
      span.style.backgroundImage = 'url("' + safe + '")';
    } else {
      span.classList.add("no-thumb");
      span.innerHTML = '<svg class="i" aria-hidden="true"><use href="#i-album"/></svg>';
    }
    return span;
  }

  window.NosMap = { loadScript: loadScript, getJSON: getJSON, loadLeaflet: loadLeaflet, loadKakao: loadKakao, osmLayer: osmLayer, photoPinEl: photoPinEl };

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
    // mode: record(기록 장소 핀) | wish(가고 싶은 곳 화면: 목록 색 핀, 다녀옴 체크)
    var mode = root.dataset.mode || "record";
    var canvas = root.querySelector("[data-map-canvas]");
    var cards = root.querySelector("[data-map-card]");
    var summary = root.querySelector("[data-map-summary]");
    var scopeButtons = Array.prototype.slice.call(root.querySelectorAll("[data-map-scope]"));
    var overlay = root.querySelector("[data-wish-overlay]");
    var photoToggle = root.querySelector("[data-photo-overlay]");
    var state = { scope: "kr", panes: {}, drawn: {}, groups: { kr: [], world: [] }, kakao: false, wishes: null, wishOn: false, photos: null, photoOn: false, matched: {} };
    // 겹쳐 보기를 켰을 때, 가고 싶은 곳과 같은 자리(100m)의 기록 장소는 그 가고 싶은 곳 색으로 (핀 하나로 보이게)
    function wishAt(p) { return kindOf(p) === "record" && state.wishOn ? state.matched[p.id] : null; }
    // 카카오 기본 핀과 같은 모양을 색만 바꿔 그린 이미지 (CSS 변수는 이미지에 못 쓰므로 지금 색 값을 읽는다)
    function pinImageUrl(color) {
      var hex = getComputedStyle(document.documentElement).getPropertyValue("--" + color).trim() || "#3396ff";
      var svg = "<svg xmlns='http://www.w3.org/2000/svg' width='28' height='38' viewBox='0 0 28 38'>" +
        "<path d='M14 1C6.8 1 1 6.6 1 13.6 1 23 14 37 14 37s13-14 13-23.4C27 6.6 21.2 1 14 1z' fill='" + hex + "' stroke='#fff' stroke-width='2'/>" +
        "<circle cx='14' cy='13.5' r='4.5' fill='#fff'/></svg>";
      return "data:image/svg+xml;charset=utf-8," + encodeURIComponent(svg);
    }

    function kindOf(p) { return p.kind || (mode === "wish" ? "wish" : "record"); }

    // ---------- 사진 줄: 작은 사진을 가로로, 날이 바뀌는 곳에 날짜 ----------
    function dayText(iso) {
      var d = iso.split("-").map(Number);
      return d[1] + "월 " + d[2] + "일";
    }
    function photoStrip(photos, total, moreUrl) {
      var strip = document.createElement("div");
      strip.className = "photo-strip";
      var lastDay = "";
      photos.forEach(function (ph) {
        if (ph.date !== lastDay) {
          lastDay = ph.date;
          var day = document.createElement("span");
          day.className = "strip-day";
          day.textContent = dayText(ph.date);
          strip.appendChild(day);
        }
        var a = document.createElement("a");
        a.className = "strip-photo";
        a.href = ph.url;
        a.setAttribute("aria-label", dayText(ph.date) + " 사진 보기");
        if (ph.thumb) {
          var img = document.createElement("img");
          img.src = ph.thumb; img.alt = ""; img.loading = "lazy"; img.decoding = "async";
          a.appendChild(img);
        } else {
          a.classList.add("no-thumb"); // 작은 사진이 없는 사진(HEIC 등): 원본은 받지 않는다
          a.innerHTML = '<svg class="i" aria-hidden="true"><use href="#i-album"/></svg>';
        }
        strip.appendChild(a);
      });
      if (total > photos.length && moreUrl) {
        var more = document.createElement("a");
        more.className = "strip-more";
        more.href = moreUrl;
        more.textContent = "전체 보기 ›";
        strip.appendChild(more);
      }
      return strip;
    }
    // 50m 안에 있는 사진 핀들 (사진 핀을 누르면 그 자리 사진을 함께 보여 준다)
    function nearby(p, list) {
      var R = 6371000, toRad = Math.PI / 180;
      return list.filter(function (q) {
        var dLat = (q.lat - p.lat) * toRad, dLng = (q.lng - p.lng) * toRad;
        var a = Math.sin(dLat / 2) * Math.sin(dLat / 2) + Math.cos(p.lat * toRad) * Math.cos(q.lat * toRad) * Math.sin(dLng / 2) * Math.sin(dLng / 2);
        return 2 * R * Math.asin(Math.sqrt(a)) <= 50;
      });
    }
    function byDate(a, b) { return a.date < b.date ? -1 : a.date > b.date ? 1 : a.id - b.id; }
    var STRIP_MAX = 60; // 사진 묶음을 눌러도 최근 60장만 줄로 (확대하면 나뉜다)

    function showCards(list) {
      cards.innerHTML = "";
      var photos = list.filter(function (p) { return kindOf(p) === "photo"; });
      var places = list.filter(function (p) { return kindOf(p) !== "photo"; });
      if (photos.length) {
        // 사진 핀 하나를 눌렀으면 그 자리(50m) 사진을 모두, 묶음이면 묶음 안 사진을
        if (photos.length === 1 && state.photos) photos = nearby(photos[0], state.photos);
        var box = document.createElement("div");
        box.className = "place-card card photo-card";
        var head = document.createElement("strong");
        head.textContent = "사진 " + photos.length + "장";
        box.appendChild(head);
        var shown = photos.slice().sort(byDate).slice(-STRIP_MAX);
        box.appendChild(photoStrip(shown, photos.length));
        if (photos.length > shown.length) {
          var note = document.createElement("small");
          note.className = "muted";
          note.textContent = "최근 " + STRIP_MAX + "장만 보여요. 지도를 확대하면 나눠 볼 수 있어요.";
          box.appendChild(note);
        }
        cards.appendChild(box);
      }
      places.forEach(function (p) {
        var card = document.createElement("div");
        card.className = "place-card card" + (kindOf(p) !== "record" ? " is-wish" : "");
        var a = document.createElement("a");
        a.className = "place-head";
        a.href = p.url + (kindOf(p) === "wish-hollow" ? "?from=record" : ""); // 겹쳐 보기 카드는 고친 뒤 기록 탭으로
        var name = document.createElement("strong");
        name.textContent = p.name;
        var addr = document.createElement("small");
        addr.textContent = p.address || "";
        var meta = document.createElement("span");
        meta.className = "meta";
        meta.textContent = kindOf(p) === "record" ? "사진 " + p.photos + "장" : (p.visited ? "다녀옴" : "가고 싶은 곳");
        a.appendChild(name); a.appendChild(addr); a.appendChild(meta);
        // 가고 싶은 곳: 들어 있는 목록 이름 (예: 부산여행). 같은 자리 기록 장소도 겹쳐 보기 중이면 함께
        var wish = wishAt(p);
        var listItems = kindOf(p) !== "record" ? p.lists : (wish ? [{ name: "가고 싶은 곳 · " + wish.name, color: wish.color }].concat(wish.lists) : null);
        if (listItems && listItems.length) {
          var lists = document.createElement("span");
          lists.className = "wish-lists";
          listItems.forEach(function (l) {
            var chip = document.createElement("span");
            chip.className = "label-chip";
            chip.style.setProperty("--c", "var(--" + l.color + ")");
            chip.textContent = l.name;
            lists.appendChild(chip);
          });
          a.appendChild(lists);
        }
        card.appendChild(a);
        // 장소 하나만 열었을 때 그 장소 사진 줄을 받아 붙인다
        if (kindOf(p) === "record" && p.photos && p.strip && places.length === 1) {
          getJSON(p.strip).then(function (data) {
            if (data.photos.length) card.appendChild(photoStrip(data.photos, data.total, data.more_url));
          }).catch(function () { /* 줄만 안 보일 뿐 */ });
        }
        cards.appendChild(card);
      });
      cards.hidden = !(photos.length || places.length);
    }
    function showSummary(scope) {
      var n = state.groups[scope].length;
      var none = mode === "wish" ? "아직 저장한 " : "아직 기록한 ";
      summary.textContent = n ? n + "곳" : none + (scope === "kr" ? "국내 장소가 없어요." : "해외 장소가 없어요.");
    }
    // 핀 모양: 기록은 기본 핀, 가고 싶은 곳은 목록 색 원(다녀옴은 체크), 겹쳐 보기는 테두리만
    function pinHtml(p) {
      var k = kindOf(p);
      if (k === "record") return null;
      if (k === "photo") return photoPinEl(p); // 문자열이 아니라 요소 (주소를 그대로 두려고)
      var cls = "wish-pin" + (k === "wish-hollow" ? " hollow" : "") + (p.visited ? " visited" : "");
      return '<span class="' + cls + '" style="--c: var(--' + (p.color || "peach") + ')"></span>';
    }

    function drawLeaflet(pane, scope, focus) {
      var L = window.L;
      var map = L.map(pane, { zoomControl: true, worldCopyJump: true });
      osmLayer(L).addTo(map);
      var marker = function (p) {
        var html = pinHtml(p);
        var size = kindOf(p) === "photo" ? [36, 36] : [22, 22];
        var wish = wishAt(p);
        var icon = html ? L.divIcon({ className: "wish-icon", html: html, iconSize: size })
          : L.divIcon({ className: "map-pin" + (wish ? " c-" + wish.color : ""), iconSize: [18, 18] });
        var m = L.marker([p.lat, p.lng], { icon: icon, keyboard: true, title: p.name || "사진" });
        m.place = p;
        m.on("click", function () { showCards([p]); });
        return m;
      };
      var cluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 50 });
      var recordMarkers = state.groups[scope].map(marker);
      cluster.addLayers(recordMarkers);
      cluster.on("clusterclick", function (e) {
        showCards(e.layer.getAllChildMarkers().map(function (m) { return m.place; }));
      });
      map.addLayer(cluster);
      // 겹쳐 보기 핀은 기록 핀과 따로: 사진은 사진끼리만 묶고, 가고 싶은 곳은 묶지 않는다
      // (기록 핀과 한 묶음이면 핀이 하나인 곳에도 합친 숫자가 떠서 헷갈린다)
      var overlayCluster = L.markerClusterGroup({ showCoverageOnHover: false, maxClusterRadius: 40 });
      overlayCluster.on("clusterclick", function (e) {
        showCards(e.layer.getAllChildMarkers().map(function (m) { return m.place; }));
      });
      map.addLayer(overlayCluster);
      var overlayLayer = L.layerGroup().addTo(map);
      var wishMarkers = [];
      var view = {
        setFocus: function (lat, lng) { map.setView([lat, lng], 15); },
        resize: function () { map.invalidateSize(); },
        setWishes: function (list) {
          // 같은 자리 가고 싶은 곳이 있는 기록 핀은 색을 바꾸고, 겹쳐 보기를 끄면 되돌린다
          recordMarkers.forEach(function (m) {
            var wish = wishAt(m.place);
            m.setIcon(L.divIcon({ className: "map-pin" + (wish ? " c-" + wish.color : ""), iconSize: [18, 18] }));
          });
          overlayCluster.clearLayers();
          overlayLayer.clearLayers();
          wishMarkers = list.map(marker);
          wishMarkers.forEach(function (m) {
            if (kindOf(m.place) === "photo") overlayCluster.addLayer(m); else overlayLayer.addLayer(m);
          });
        },
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
      // 가고 싶은 곳 핀은 카카오 기본 마커 대신 같은 모양의 커스텀 오버레이로
      var overlayPin = function (p) {
        var el = document.createElement("button");
        el.type = "button";
        el.className = "wish-icon";
        el.setAttribute("aria-label", p.name || "사진");
        var pin = pinHtml(p);
        if (typeof pin === "string") el.innerHTML = pin; else el.appendChild(pin);
        el.addEventListener("click", function () { showCards([p]); });
        return new kakao.maps.CustomOverlay({ position: new kakao.maps.LatLng(p.lat, p.lng), content: el, yAnchor: 0.5, clickable: true });
      };
      // 기록 핀(Marker)과 가고 싶은 곳 핀(CustomOverlay)을 한 묶음(클러스터러)에 넣는다
      var byMarker = [];
      var pinOf = function (p) {
        var m;
        if (kindOf(p) !== "record") m = overlayPin(p);
        else {
          var wish = wishAt(p);
          var opts = { position: new kakao.maps.LatLng(p.lat, p.lng), title: p.name };
          if (wish) opts.image = new kakao.maps.MarkerImage(pinImageUrl(wish.color), new kakao.maps.Size(28, 38), { offset: new kakao.maps.Point(14, 37) });
          m = new kakao.maps.Marker(opts);
          m.wishColor = wish ? wish.color : "";
          kakao.maps.event.addListener(m, "click", function () { showCards([p]); });
        }
        byMarker.push({ marker: m, place: p });
        return m;
      };
      // 묶음 숫자를 누르면: 그 안의 장소·사진을 카드로 보여 주고 한 단계 확대한다
      // (카카오는 disableClickZoom 을 켜야 clusterclick 이 온다)
      var onCluster = function (c) {
        var inside = c.getMarkers();
        showCards(byMarker.filter(function (x) { return inside.indexOf(x.marker) !== -1; }).map(function (x) { return x.place; }));
        map.setLevel(Math.max(1, map.getLevel() - 1), { anchor: c.getCenter(), animate: true });
      };
      var clusterer = new kakao.maps.MarkerClusterer({ map: map, averageCenter: true, minLevel: 6, disableClickZoom: true });
      clusterer.addMarkers(state.groups[scope].map(pinOf));
      kakao.maps.event.addListener(clusterer, "clusterclick", onCluster);
      // 겹쳐 보기 핀은 기록 묶음과 따로: 사진은 사진끼리만 묶고, 가고 싶은 곳은 묶지 않고 바로 지도에
      var overlayClusterer = new kakao.maps.MarkerClusterer({ map: map, averageCenter: true, minLevel: 6, gridSize: 40, disableClickZoom: true });
      kakao.maps.event.addListener(overlayClusterer, "clusterclick", onCluster);
      var wishOverlays = [];
      var view = {
        setFocus: function (lat, lng) { map.setLevel(3); map.setCenter(new kakao.maps.LatLng(lat, lng)); },
        resize: function () { map.relayout(); },
        setWishes: function (list) {
          // 기록 핀 색: 같은 자리 가고 싶은 곳 색이 바뀐 핀만 새로 만들어 바꿔 끼운다
          byMarker.slice().forEach(function (x) {
            if (kindOf(x.place) !== "record") return;
            var wish = wishAt(x.place);
            if ((wish ? wish.color : "") === x.marker.wishColor) return;
            clusterer.removeMarker(x.marker);
            byMarker.splice(byMarker.indexOf(x), 1);
            clusterer.addMarker(pinOf(x.place));
          });
          overlayClusterer.clear();
          wishOverlays.forEach(function (o) { o.setMap(null); });
          byMarker = byMarker.filter(function (x) { return wishOverlays.indexOf(x.marker) === -1; });
          wishOverlays = list.map(pinOf);
          var photos = [];
          wishOverlays.forEach(function (o, i) {
            if (kindOf(list[i]) === "photo") photos.push(o); else o.setMap(map);
          });
          overlayClusterer.addMarkers(photos);
        },
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

    // 겹쳐 보이는 핀: 가고 싶은 곳(켰을 때) + 사진(켰을 때)
    function wishesFor(scope) {
      var list = [];
      if (state.wishOn && state.wishes) list = list.concat(state.wishes.filter(function (p) { return p.scope === scope; }));
      if (state.photoOn && state.photos) list = list.concat(state.photos.filter(function (p) { return p.scope === scope; }));
      return list;
    }

    // 기록 지도의 "사진도 보기": 장소에 안 묶인 사진을 작은 사진 핀으로 (기기에 기억, 처음엔 켬)
    function setPhotos(on) {
      state.photoOn = on;
      try { localStorage.setItem("nos.photoOverlay", on ? "1" : "0"); } catch (e) { /* 괜찮다 */ }
      var apply = function () {
        Object.keys(state.drawn).forEach(function (k) { state.drawn[k].setWishes(wishesFor(k)); });
      };
      if (!on || state.photos) return apply();
      getJSON(root.dataset.photoUrl).then(function (data) {
        state.photos = data.photos.map(function (p) {
          p.kind = "photo";
          p.scope = scopeOf(p, state.kr, state.world);
          return p;
        });
        apply();
      }).catch(function () { /* 사진 핀만 안 보일 뿐 */ });
    }

    function show(scope, focus) {
      state.scope = scope;
      scopeButtons.forEach(function (b) {
        var on = b.dataset.mapScope === scope;
        b.classList.toggle("on", on);
        b.setAttribute("aria-pressed", on ? "true" : "false");
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
          state.drawn[scope].setWishes(wishesFor(scope));
          return;
        } catch (e) {
          state.kakao = false; // 카카오맵이 실렸어도 지도를 못 만들면(도메인 미등록 등) Leaflet 으로
          pane.innerHTML = "";
        }
      }
      state.drawn[scope] = drawLeaflet(pane, scope, focus);
      state.drawn[scope].setWishes(wishesFor(scope));
    }

    // 기록 지도의 "가고 싶은 곳도 보기": 아직 안 다녀온 곳을 테두리 핀으로 겹친다 (기기에 기억)
    function setOverlay(on) {
      state.wishOn = on;
      try { localStorage.setItem("nos.wishOverlay", on ? "1" : "0"); } catch (e) { /* 괜찮다 */ }
      var apply = function () {
        Object.keys(state.drawn).forEach(function (k) { state.drawn[k].setWishes(wishesFor(k)); });
      };
      if (!on || state.wishes) return apply();
      getJSON(root.dataset.wishUrl + "?open=1").then(function (data) {
        state.matched = {};
        (data.matched || []).forEach(function (m) { state.matched[m.place] = m; });
        state.wishes = data.places.map(function (p) {
          p.kind = "wish-hollow";
          p.scope = scopeOf(p, state.kr, state.world);
          return p;
        });
        apply();
      }).catch(function () { /* 겹쳐 보기만 안 될 뿐 */ });
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
        state.kr = kr; state.world = world;
        r[0].places.forEach(function (p) { state.groups[scopeOf(p, kr, world)].push(p); });
        var focus = null;
        var raw = new URLSearchParams(location.search).get("focus");
        if (raw) {
          var parts = raw.split(",").map(Number);
          if (parts.length === 2 && !parts.some(isNaN)) focus = { lat: parts[0], lng: parts[1], scope: scopeOf({ lat: parts[0], lng: parts[1] }, kr, world) };
        }
        if (overlay && overlay.checked) state.wishOn = true;
        show(focus ? focus.scope : state.groups.kr.length || !state.groups.world.length ? "kr" : "world", focus);
        if (state.wishOn) setOverlay(true);
        if (photoToggle && photoToggle.checked) setPhotos(true);
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
    if (overlay) {
      try { overlay.checked = localStorage.getItem("nos.wishOverlay") === "1"; } catch (e) { /* 없음 */ }
      overlay.addEventListener("change", function () {
        if (state.kr) return setOverlay(overlay.checked);
        // 지도를 불러오는 중이면 기억만 해 둔다 (다 불러오면 체크 상태를 따른다)
        try { localStorage.setItem("nos.wishOverlay", overlay.checked ? "1" : "0"); } catch (e) { /* 괜찮다 */ }
      });
    }
    if (photoToggle) {
      try { photoToggle.checked = localStorage.getItem("nos.photoOverlay") !== "0"; } catch (e) { /* 없음: 켬 */ }
      photoToggle.addEventListener("change", function () {
        if (state.kr) return setPhotos(photoToggle.checked);
        try { localStorage.setItem("nos.photoOverlay", photoToggle.checked ? "1" : "0"); } catch (e) { /* 괜찮다 */ }
      });
    }
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

  // 색칠 지도(coloring-map.js)도 같은 지역 판정 함수를 쓴다
  window.NosMap.geo = { features: features, contains: contains, find: find, polygonsOf: polygonsOf, topojsonUrl: LIBS.topojson };

  // 기록 지도는 보일 때 그린다 (색칠 지도를 보고 있으면 핀 지도로 바꿀 때 그린다: 숨은 칸에서 그리면 크기가 0)
  var record = document.querySelector("[data-record-map]");
  if (record) {
    if (record.dataset.view !== "color") recordMap(record);
    else document.addEventListener("nos:record-view", function first(e) {
      if (e.detail !== "pin") return;
      document.removeEventListener("nos:record-view", first);
      recordMap(record);
    });
  }
  Array.prototype.forEach.call(document.querySelectorAll("[data-mini-map]"), miniMap);
})();
