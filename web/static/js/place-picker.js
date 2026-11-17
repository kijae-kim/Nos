// 장소 기록하기의 위치 고르기: 이름 검색(기본), 지도에서 찍기, 사진에서.
// 고른 위치는 폼의 숨은 칸(latitude, longitude, address, place_url, from_photo)에 넣는다.
// 지도 불러오기는 map.js 의 window.NosMap 을 쓴다. 고르기 지도는 국내외 모두 되도록 Leaflet 이다.
(function () {
  "use strict";
  var box = document.querySelector("[data-place-picker]");
  if (!box || !window.NosMap) return;
  var form = box.closest("form");
  var $ = function (sel) { return box.querySelector(sel); };
  var field = function (name) { return form.querySelector('[name="' + name + '"]'); };

  var picked = $("[data-picked]"), pickedText = $("[data-picked-text]");
  var input = $("[data-search-input]"), results = $("[data-search-results]");
  var msg = $("[data-pick-msg]"), photosBox = $("[data-pick-photos]");
  var mapBox = $("[data-pick-mapbox]"), hereBtn = $("[data-pick-here]");
  var map = null, marker = null, mode = null;

  function say(text) { msg.textContent = text || ""; msg.hidden = !text; }
  function closePanels() {
    results.hidden = true; photosBox.hidden = true; hereBtn.hidden = true;
    mode = null;
    box.classList.remove("picking-map");
  }

  // 작은 지도 (고른 곳 보기, 지도에서 찍기 둘 다)
  function ensureMap(lat, lng, zoom) {
    return window.NosMap.loadLeaflet().then(function () {
      var L = window.L;
      mapBox.hidden = false;
      if (!map) {
        map = L.map(mapBox, { scrollWheelZoom: false });
        window.NosMap.osmLayer(L).addTo(map);
      }
      map.invalidateSize();
      map.setView([lat, lng], zoom);
      return map;
    });
  }
  function showPin(lat, lng) {
    ensureMap(lat, lng, 16).then(function (m) {
      var L = window.L;
      if (marker) marker.setLatLng([lat, lng]);
      else marker = L.marker([lat, lng], { icon: L.divIcon({ className: "map-pin", iconSize: [18, 18] }) }).addTo(m);
    });
  }

  function setPicked(p) {
    field("latitude").value = String(p.lat);
    field("longitude").value = String(p.lng);
    field("address").value = p.address || "";
    field("place_url").value = p.url || "";
    field("from_photo").value = p.fromPhoto ? String(p.fromPhoto) : "";
    var title = field("title");
    if (title && !title.value.trim() && p.name) title.value = p.name;
    pickedText.textContent = p.address || p.label || "고른 위치";
    picked.hidden = false;
    closePanels();
    say("");
    showPin(p.lat, p.lng);
  }

  // ---------- 이름 검색 ----------
  function search() {
    var q = input.value.trim();
    if (!q) return input.focus();
    closePanels();
    say("찾고 있어요…");
    window.NosMap.getJSON(box.dataset.searchUrl + "?q=" + encodeURIComponent(q)).then(function (data) {
      results.innerHTML = "";
      if (!data.results.length) return say("찾는 곳이 없어요. 지도에서 직접 찍어 볼까요?");
      say("");
      data.results.forEach(function (r) {
        var li = document.createElement("li");
        var b = document.createElement("button");
        b.type = "button";
        var name = document.createElement("strong");
        name.textContent = r.name;
        var addr = document.createElement("small");
        addr.textContent = (r.source === "osm" ? "OpenStreetMap · " : "") + (r.address || "");
        b.appendChild(name); b.appendChild(addr);
        b.addEventListener("click", function () { setPicked(r); });
        li.appendChild(b);
        results.appendChild(li);
      });
      results.hidden = false;
    }).catch(function () { say("검색이 잠시 안 돼요. 지도에서 직접 찍어 볼까요?"); });
  }
  $("[data-search-go]").addEventListener("click", search);
  input.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && !e.isComposing) { e.preventDefault(); search(); } // 한글 입력 중 엔터는 글자 확정
  });
  // 안드로이드 키보드의 "검색" 키는 엔터 이벤트 없이 폼을 보내기도 한다 → 검색 칸에 있을 때는 보내지 않고 검색한다
  form.addEventListener("submit", function (e) {
    if (document.activeElement === input) { e.preventDefault(); search(); }
  });

  // ---------- 지도에서 찍기 ----------
  $("[data-pick-map]").addEventListener("click", function () {
    closePanels();
    say("지도를 움직여 가운데 핀을 맞춘 뒤 '여기로'를 눌러 주세요.");
    mode = "map";
    box.classList.add("picking-map");
    var lat = parseFloat(field("latitude").value), lng = parseFloat(field("longitude").value);
    var has = !isNaN(lat) && !isNaN(lng);
    ensureMap(has ? lat : 37.5665, has ? lng : 126.978, has ? 16 : 12).then(function () {
      if (marker) { marker.remove(); marker = null; }
      hereBtn.hidden = false;
    }).catch(function () { say("지도를 불러오지 못했어요. 잠시 뒤 다시 해 볼까요?"); });
  });
  hereBtn.addEventListener("click", function () {
    if (!map) return;
    var c = map.getCenter();
    setPicked({ lat: +c.lat.toFixed(6), lng: +c.lng.toFixed(6), label: "지도에서 고른 위치" });
  });

  // ---------- 사진에서 (장소 기록만, 가고 싶은 곳에는 버튼이 없다) ----------
  var photoBtn = $("[data-pick-photo]");
  if (photoBtn) photoBtn.addEventListener("click", function () {
    closePanels();
    say("사진을 불러오고 있어요…");
    window.NosMap.getJSON(box.dataset.photosUrl).then(function (data) {
      photosBox.innerHTML = "";
      if (!data.photos.length) return say("위치가 있는 사진이 아직 없어요. 검색이나 지도에서 골라 주세요.");
      say("이곳에서 찍은 사진을 하나 골라 주세요. 그 사진도 이 장소에 연결돼요.");
      data.photos.forEach(function (p) {
        var b = document.createElement("button");
        b.type = "button";
        b.className = "tile";
        b.setAttribute("aria-label", p.taken + " 사진의 위치로");
        var img = document.createElement("img");
        img.loading = "lazy"; img.decoding = "async"; img.alt = ""; img.src = p.src;
        b.appendChild(img);
        b.addEventListener("click", function () {
          setPicked({ lat: p.lat, lng: p.lng, label: p.taken + " 사진의 위치", fromPhoto: p.id });
        });
        photosBox.appendChild(b);
      });
      photosBox.hidden = false;
    }).catch(function () { say("사진을 불러오지 못했어요. 잠시 뒤 다시 해 볼까요?"); });
  });

  // 바꾸기: 고른 줄을 접고 검색 칸으로
  $("[data-pick-reset]").addEventListener("click", function () {
    picked.hidden = true;
    input.focus();
  });

  // 고치기 화면: 이미 있는 위치를 작은 지도에 보여 준다
  var lat0 = parseFloat(field("latitude").value), lng0 = parseFloat(field("longitude").value);
  if (!isNaN(lat0) && !isNaN(lng0)) showPin(lat0, lng0);
})();
