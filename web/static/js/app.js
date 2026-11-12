// 공통 동작: 팔레트·화면 모드, + 버튼, 탭 전환, 초대 코드 칸, 이름표 넣기, D-day 장면, 시작·로딩 화면
(function () {
  var root = document.documentElement;
  var $$ = function (selector, scope) {
    return Array.prototype.slice.call((scope || document).querySelectorAll(selector));
  };
  var store = function (key, value) {
    try {
      if (value === null) localStorage.removeItem(key);
      else localStorage.setItem(key, value);
    } catch (e) {}
  };
  var reduceMotion = function () {
    return window.matchMedia("(prefers-reduced-motion: reduce)").matches;
  };

  // 팔레트 (배 / 여정)
  function markPalette() {
    $$("[data-palette-choice]").forEach(function (b) {
      b.classList.toggle("on", b.dataset.paletteChoice === root.dataset.theme);
    });
  }
  $$("[data-palette-choice]").forEach(function (b) {
    b.addEventListener("click", function () {
      root.dataset.theme = b.dataset.paletteChoice;
      store("palette", b.dataset.paletteChoice);
      markPalette();
    });
  });
  markPalette();

  // 화면 모드 (기기 설정 / 라이트 / 다크)
  var systemDark = window.matchMedia("(prefers-color-scheme: dark)");
  function applyMode(choice) {
    var mode = choice === "system" ? (systemDark.matches ? "dark" : "light") : choice;
    root.dataset.mode = mode;
    store("mode", choice === "system" ? null : choice);
    $$("[data-mode-choice]").forEach(function (b) {
      var on = b.dataset.modeChoice === choice;
      b.classList.toggle("on", on);
      b.setAttribute("aria-checked", String(on));
    });
  }
  var savedMode = (function () {
    try { return localStorage.getItem("mode") || "system"; } catch (e) { return "system"; }
  })();
  $$("[data-mode-choice]").forEach(function (b) {
    b.addEventListener("click", function () { applyMode(b.dataset.modeChoice); });
  });
  applyMode(savedMode);

  // + 버튼: 빠른 추가 메뉴 열고 닫기 (휴대폰)
  var app = document.getElementById("app");
  var fab = document.getElementById("fab");
  var dim = document.getElementById("dim");
  function setOpen(open) {
    app.classList.toggle("open", open);
    fab.setAttribute("aria-expanded", String(open));
  }
  if (fab) fab.addEventListener("click", function () { setOpen(!app.classList.contains("open")); });
  if (dim) dim.addEventListener("click", function () { setOpen(false); });

  // 탭 전환형 선택 (연결 방식, 앨범 보기): data-tabs 안의 버튼은 data-target 패널을 연다
  $$("[data-tabs]").forEach(function (group) {
    var buttons = $$("button", group);
    buttons.forEach(function (b, i) {
      b.addEventListener("click", function () {
        buttons.forEach(function (x) { x.classList.toggle("on", x === b); });
        var thumb = group.querySelector(".thumb");
        if (thumb) thumb.style.transform = "translateX(" + i * 100 + "%)";
        var target = b.dataset.target;
        $$(".view").forEach(function (panel) {
          if (panel.parentElement === group.parentElement) panel.classList.toggle("on", panel.id === target);
        });
      });
    });
  });

  // 이름표 바로 넣기: 누르면 일정 글 끝에 @이름 또는 #이름 이 붙는다
  var textField = document.getElementById("id_text");
  $$("[data-insert]").forEach(function (b) {
    b.addEventListener("click", function () {
      if (!textField) return;
      var token = b.dataset.insert;
      var value = textField.value.replace(/\s+$/, "");
      textField.value = (value ? value + " " : "") + token + " ";
      textField.focus();
    });
  });

  // 일정 시간: 시작을 고르면 끝은 2시간 뒤로 들어가고, +15분·+30분·+1시간 버튼으로 끝 시간을 조정한다
  var startTime = document.getElementById("id_start_time");
  var endTime = document.getElementById("id_end_time");
  if (startTime && endTime) {
    var AUTO_MINUTES = 120;
    var autoEnd = !endTime.value;
    var pad = function (n) { return (n < 10 ? "0" : "") + n; };
    var toMinutes = function (v) { var p = v.split(":"); return parseInt(p[0], 10) * 60 + parseInt(p[1], 10); };
    var fromMinutes = function (m) { m = ((m % 1440) + 1440) % 1440; return pad(Math.floor(m / 60)) + ":" + pad(m % 60); };
    var nextQuarter = function () {
      var now = new Date();
      return fromMinutes(Math.ceil((now.getHours() * 60 + now.getMinutes()) / 15) * 15);
    };

    startTime.addEventListener("change", function () {
      if (!startTime.value) return;
      if (autoEnd) endTime.value = fromMinutes(toMinutes(startTime.value) + AUTO_MINUTES);
    });
    endTime.addEventListener("input", function () { autoEnd = false; });

    $$("[data-end-add]").forEach(function (b) {
      b.addEventListener("click", function () {
        if (!startTime.value) startTime.value = nextQuarter();
        var base = endTime.value ? toMinutes(endTime.value) : toMinutes(startTime.value) + AUTO_MINUTES;
        endTime.value = fromMinutes(base + parseInt(b.dataset.endAdd, 10));
      });
    });
  }

  // 큰 사진은 올리기 전에 줄인다: 긴 변 2560px, JPEG. 배포 서버는 요청 하나에 4.5MB까지만 받는다.
  // 줄이면서 위치 같은 촬영 정보도 빠진다. 줄일 수 없거나 줄여도 크지 않으면 원본을 그대로 쓴다.
  var SHRINK_ABOVE = 1.5 * 1024 * 1024, MAX_EDGE = 2560;
  function shrinkImage(file) {
    return new Promise(function (resolve) {
      if (file.size <= SHRINK_ABOVE || file.type === "image/gif") return resolve(file);
      var url = URL.createObjectURL(file);
      var img = new Image();
      img.onerror = function () { URL.revokeObjectURL(url); resolve(file); };
      img.onload = function () {
        URL.revokeObjectURL(url);
        var scale = Math.min(1, MAX_EDGE / Math.max(img.naturalWidth, img.naturalHeight));
        var canvas = document.createElement("canvas");
        canvas.width = Math.round(img.naturalWidth * scale);
        canvas.height = Math.round(img.naturalHeight * scale);
        var ctx = canvas.getContext("2d");
        ctx.fillStyle = "#fff"; // 투명한 PNG 가 JPEG 에서 검게 나오지 않도록
        ctx.fillRect(0, 0, canvas.width, canvas.height);
        ctx.drawImage(img, 0, 0, canvas.width, canvas.height);
        canvas.toBlob(function (blob) {
          if (!blob || blob.size >= file.size) return resolve(file);
          var name = file.name.replace(/\.[^.]+$/, "") + ".jpg";
          resolve(new File([blob], name, { type: "image/jpeg", lastModified: file.lastModified }));
        }, "image/jpeg", 0.85);
      };
      img.src = url;
    });
  }
  var sizeText = function (bytes) { return (bytes / 1024 / 1024).toFixed(1) + "MB"; };

  // 사진 칸: 누르거나 파일을 끌어 놓아 고르고, 고른 사진을 미리 보여 준다
  $$("[data-dropzone]").forEach(function (zone) {
    var input = zone.querySelector('input[type="file"]');
    var preview = zone.querySelector("[data-preview]");
    var hint = zone.querySelector("[data-hint]");
    if (!input) return;
    var form = zone.closest("form");
    var maxBytes = parseInt(input.dataset.maxBytes, 10) || Infinity;
    var busy = false;
    var show = function (file) {
      if (!file || file.type.indexOf("image/") !== 0) return;
      preview.src = URL.createObjectURL(file);
      preview.hidden = false;
      if (hint) hint.textContent = file.name;
    };
    // 고른 파일을 줄이고, 입력 칸에 줄인 파일을 넣은 뒤 미리 보여 준다
    var take = function (file) {
      if (!file) return;
      busy = true;
      zone.classList.add("working");
      if (hint) hint.textContent = "사진을 준비하는 중…";
      shrinkImage(file).then(function (ready) {
        busy = false;
        zone.classList.remove("working");
        if (ready.size > maxBytes) {
          input.value = "";
          preview.hidden = true;
          if (hint) hint.textContent = "사진이 너무 커요 (" + sizeText(ready.size) + "). " + sizeText(maxBytes) + " 이하로 골라 주세요.";
          return;
        }
        if (ready !== file || input.files[0] !== file) {
          var transfer = new DataTransfer();
          transfer.items.add(ready);
          input.files = transfer.files;
        }
        show(ready);
      });
    };
    input.addEventListener("change", function () { take(input.files[0]); });
    // 사진을 줄이는 동안에는 보내지 않는다
    if (form) {
      form.addEventListener("submit", function (e) {
        if (busy) { e.preventDefault(); if (hint) hint.textContent = "사진을 준비하고 있어요. 잠시 뒤 다시 눌러 주세요."; }
      });
    }
    zone.addEventListener("dragover", function (e) { e.preventDefault(); zone.classList.add("dragging"); });
    zone.addEventListener("dragleave", function () { zone.classList.remove("dragging"); });
    zone.addEventListener("drop", function (e) {
      e.preventDefault();
      zone.classList.remove("dragging");
      take(e.dataTransfer.files[0]);
    });
  });

  // 초대 코드 6칸: 한 글자 입력하면 다음 칸으로, 지우면 이전 칸으로. 숨은 입력에 합쳐서 보낸다.
  $$("[data-code-inputs]").forEach(function (wrap) {
    var boxes = $$("input", wrap);
    var hidden = document.getElementById("code-hidden");
    function sync() {
      if (hidden) hidden.value = boxes.map(function (x) { return x.value; }).join("").toUpperCase();
    }
    if (hidden && hidden.value) {
      hidden.value.split("").forEach(function (ch, i) { if (boxes[i]) boxes[i].value = ch; });
    }
    boxes.forEach(function (box, i) {
      box.addEventListener("input", function () {
        box.value = box.value.slice(-1).toUpperCase();
        if (box.value && boxes[i + 1]) boxes[i + 1].focus();
        sync();
      });
      box.addEventListener("keydown", function (e) {
        if (e.key === "Backspace" && !box.value && boxes[i - 1]) boxes[i - 1].focus();
      });
      box.addEventListener("paste", function (e) {
        var text = (e.clipboardData || window.clipboardData).getData("text").replace(/\s/g, "");
        if (!text) return;
        e.preventDefault();
        text.slice(0, boxes.length).toUpperCase().split("").forEach(function (ch, j) { boxes[j].value = ch; });
        var next = boxes[Math.min(text.length, boxes.length) - 1];
        if (next) next.focus();
        sync();
      });
    });
    wrap.closest("form").addEventListener("submit", sync);
  });

  // 초대 코드 복사
  $$("[data-copy]").forEach(function (button) {
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
  $$("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (!window.confirm(form.dataset.confirm)) event.preventDefault();
    });
  });

  // ---------- D-day 장면 ----------
  // 장면의 크기는 CSS(가로에 맞춘 비율)가 정하고, 깃발과 배의 자리는 여기서 길 위의 점으로 잡는다.
  // 길 좌표(342 × 150)를 비율로 바꿔 쓰므로 카드가 좁아지거나 넓어져도 같이 맞는다.
  var VIEW_W = 342, VIEW_H = 150;

  function pointAt(path, fraction) {
    var len = path.getTotalLength();
    return path.getPointAtLength(len * fraction);
  }

  function placeMarks(scene) {
    var path = scene.querySelector("[data-ridge]");
    if (!path) return;
    $$(".mark", scene).forEach(function (mark) {
      var p = pointAt(path, parseFloat(mark.dataset.at));
      mark.style.left = (p.x / VIEW_W * 100) + "%";
      mark.style.top = (p.y / VIEW_H * 100) + "%";
    });
  }

  function placeMover(scene, mover, fraction) {
    var path = scene.querySelector("[data-ridge]");
    var p = pointAt(path, fraction);
    var ahead = pointAt(path, Math.min(1, fraction + 0.01));
    var angle = Math.atan2(ahead.y - p.y, ahead.x - p.x) * 180 / Math.PI;
    mover.style.left = (p.x / VIEW_W * 100) + "%";
    mover.style.top = (p.y / VIEW_H * 100) + "%";
    mover.style.transform = "translate(-50%, -92%)" + (mover.dataset.rotate === "auto" ? " rotate(" + angle + "deg)" : "");
  }

  // 배(또는 사람)가 길을 따라 from → to 까지 움직인다. 같은 장면을 다시 부르면 처음부터 다시 간다.
  function sailScene(scene) {
    var path = scene.querySelector("[data-ridge]");
    var mover = scene.querySelector("[data-mover]");
    if (!path || !mover) return;
    var FROM = 0.04, TO = 0.77, DURATION = 3200, DELAY = 250;
    if (scene._frame) cancelAnimationFrame(scene._frame);
    if (reduceMotion()) {
      placeMover(scene, mover, TO);
      return;
    }
    var startedAt = null;
    function step(now) {
      if (startedAt === null) startedAt = now;
      var elapsed = now - startedAt - DELAY;
      if (elapsed < 0) {
        placeMover(scene, mover, FROM);
      } else {
        var t = Math.min(1, elapsed / DURATION);
        var eased = 1 - Math.pow(1 - t, 3);
        placeMover(scene, mover, FROM + (TO - FROM) * eased);
        if (t >= 1) { scene._frame = null; return; }
      }
      scene._frame = requestAnimationFrame(step);
    }
    scene._frame = requestAnimationFrame(step);
  }

  // 출발 애니메이션 + 숫자 올라가기
  function countUp(card) {
    var num = card.querySelector("[data-count]");
    if (!num || reduceMotion()) return;
    var target = parseInt(num.dataset.count, 10);
    var from = Math.max(0, target - 35);
    var start = performance.now();
    (function tick(now) {
      var t = Math.min(1, (now - start) / 1400);
      var eased = 1 - Math.pow(1 - t, 3);
      num.textContent = Math.round(from + (target - from) * eased);
      if (t < 1) requestAnimationFrame(tick);
    })(start);
  }

  function sail(card) {
    card.classList.remove("sailing");
    void card.offsetWidth; // 애니메이션을 다시 시작한다
    card.classList.add("sailing");
    countUp(card);
    $$("[data-scene]", card).forEach(sailScene);
  }

  $$("[data-scene]").forEach(placeMarks);
  $$(".dday").forEach(function (card) {
    sail(card);
    card.addEventListener("click", function () { sail(card); });
  });

  // 하루 종일: 켜면 시간 칸을 숨긴다
  var allDay = document.getElementById("id_all_day");
  var timeFields = document.querySelector("[data-time-fields]");
  if (allDay && timeFields) {
    var syncAllDay = function () { timeFields.hidden = allDay.checked; };
    allDay.addEventListener("change", syncAllDay);
    syncAllDay();
  }

  // ---------- 시작 화면 ----------
  // 점들이 물결치는 바탕. 손가락이나 마우스를 움직이면 물결의 중심이 따라온다. 멈추는 함수를 돌려준다.
  function dotField(canvas) {
    var ctx = canvas.getContext("2d");
    var dpr = window.devicePixelRatio || 1;
    var W = canvas.clientWidth, H = canvas.clientHeight, GAP = 22;
    canvas.width = W * dpr; canvas.height = H * dpr; ctx.scale(dpr, dpr);
    var cx = W / 2, cy = H / 2, tx = cx, ty = cy, frame = null, still = reduceMotion();
    var onMove = function (e) { tx = e.clientX; ty = e.clientY; };
    canvas.parentElement.addEventListener("pointermove", onMove);
    function draw(now) {
      var t = now / 1000;
      cx += (tx - cx) * 0.08; cy += (ty - cy) * 0.08;
      ctx.clearRect(0, 0, W, H);
      ctx.fillStyle = "#fff";
      for (var row = 0, y = GAP / 2; y < H; y += GAP * 0.866, row++) {
        for (var x = row % 2 ? GAP : GAP / 2; x < W; x += GAP) {
          var dist = Math.sqrt((x - cx) * (x - cx) + (y - cy) * (y - cy));
          var wave = 0.5 + 0.5 * Math.sin(dist * 0.05 - t * 2.4);
          var band = Math.exp(-Math.pow((dist - 210) / 70, 2)); // 로고와 글자 자리는 비우고 바깥에서 물결친다
          var amount = wave * band;
          ctx.globalAlpha = 0.12 + 0.45 * amount;
          ctx.beginPath(); ctx.arc(x, y, 0.8 + 3.2 * amount, 0, 6.2832); ctx.fill();
        }
      }
      if (!still) frame = requestAnimationFrame(draw);
    }
    frame = requestAnimationFrame(draw);
    return function () {
      still = true;
      if (frame) cancelAnimationFrame(frame);
      canvas.parentElement.removeEventListener("pointermove", onMove);
    };
  }

  var splash = document.getElementById("splash");
  if (splash && root.classList.contains("splash-on")) {
    var stopDots = dotField(splash.querySelector("canvas"));
    var left = false;
    var leaveSplash = function () {
      if (left) return;
      left = true;
      try { sessionStorage.setItem("splashed", "1"); } catch (e) {}
      splash.classList.add("leaving");
      setTimeout(function () { root.classList.remove("splash-on"); stopDots(); }, 460);
    };
    splash.addEventListener("click", leaveSplash);
    setTimeout(leaveSplash, reduceMotion() ? 800 : 2400);
  }

  // ---------- 로딩 화면 ----------
  // 화면을 옮기거나 저장할 때, 다음 화면이 0.35초 안에 안 뜨면 보여 준다.
  var loadTimer = null, giveUpTimer = null;
  function hideLoader() {
    clearTimeout(loadTimer); clearTimeout(giveUpTimer);
    root.classList.remove("is-loading");
  }
  function showLoaderSoon() {
    hideLoader();
    loadTimer = setTimeout(function () { root.classList.add("is-loading"); }, 350);
    giveUpTimer = setTimeout(hideLoader, 15000); // 화면이 안 바뀌는 경우(파일 내려받기 등)에 대비
  }
  document.addEventListener("click", function (e) {
    var link = e.target.closest ? e.target.closest("a[href]") : null;
    if (!link || e.defaultPrevented || e.button !== 0 || e.metaKey || e.ctrlKey || e.shiftKey || e.altKey) return;
    if ((link.target && link.target !== "_self") || link.hasAttribute("download")) return;
    var url;
    try { url = new URL(link.href); } catch (err) { return; }
    if (url.origin !== location.origin) return;
    if (url.pathname === location.pathname && url.search === location.search) return; // 같은 화면 안의 이동
    showLoaderSoon();
  });
  document.addEventListener("submit", function (e) {
    if (!e.defaultPrevented) showLoaderSoon();
  });
  window.addEventListener("pageshow", hideLoader); // 뒤로 가기로 돌아왔을 때

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }
})();
