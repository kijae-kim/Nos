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
  var csrfToken = function () {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  };
  // 테마·화면 모드를 계정에도 저장한다 (로그인했을 때만). 실패해도 이 기기에는 이미 적용돼 있다.
  function saveAppearance(data) {
    if (!root.dataset.accountPalette) return;
    var body = new URLSearchParams(data);
    fetch("/me/appearance/", {
      method: "POST",
      body: body,
      credentials: "same-origin",
      headers: { "X-CSRFToken": csrfToken(), Accept: "application/json" }
    }).then(function (res) {
      if (!res.ok) return;
      if (data.palette) root.dataset.accountPalette = data.palette;
      if (data.mode) root.dataset.accountMode = data.mode;
    }).catch(function () {});
  }
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
      saveAppearance({ palette: b.dataset.paletteChoice });
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
    b.addEventListener("click", function () {
      applyMode(b.dataset.modeChoice);
      saveAppearance({ mode: b.dataset.modeChoice });
    });
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

  // 숫자로 치는 날짜 칸 (config/fields.py): 20261113 → 2026.11.13 처럼 점을 넣는다.
  // 숫자만 친 경우에만 바꾸고, 사용자가 직접 점·줄표를 넣으면 그대로 둔다.
  $$("input[data-date-type]").forEach(function (input) {
    input.addEventListener("input", function (e) {
      if (e.inputType && e.inputType.indexOf("delete") === 0) return; // 지울 때는 건드리지 않는다
      var raw = input.value;
      if (/[^\d.]/.test(raw) || /\.$/.test(raw)) return; // 줄표·빗금을 쓰거나 점을 직접 찍었으면 그대로
      // 2026.1. 처럼 직접 짧게 끊어 쓰는 중이면 그대로 둔다
      var parts = raw.split(".");
      if (parts.length > 1 && (parts[0].length !== 4 || (parts.length > 2 && parts[1].length !== 2))) return;
      var digits = raw.replace(/\D/g, "").slice(0, 8);
      var out = digits.slice(0, 4);
      if (digits.length > 4) out += "." + digits.slice(4, 6);
      if (digits.length > 6) out += "." + digits.slice(6, 8);
      if (out !== raw) input.value = out;
    });
  });

  // 바꾸면 바로 저장하는 폼 (구독 설정의 스위치 등)
  $$("form[data-autosubmit]").forEach(function (form) {
    form.addEventListener("change", function () {
      if (form.requestSubmit) form.requestSubmit(); else form.submit();
    });
  });
  // 누르면 칸의 글자를 모두 고른다 (구독 주소)
  $$("[data-select-all]").forEach(function (input) {
    input.addEventListener("focus", function () { input.select(); });
  });

  // 외부 썸네일이 깨지면 숨긴다 (사이트가 그림을 지웠거나 막았을 때)
  $$("img[data-hide-broken]").forEach(function (img) {
    var hide = function () { img.hidden = true; };
    if (img.complete && !img.naturalWidth) hide();
    img.addEventListener("error", hide);
  });

  // ---------- 취향 링크 미리보기 ----------
  // 링크를 붙여 넣으면 제목·썸네일을 보여 주고, 비어 있는 제목과 분류를 채운다. 이미 적은 것은 건드리지 않는다.
  $$("input[data-link-preview]").forEach(function (input) {
    var form = input.form;
    var card = form.querySelector("[data-link-card]");
    var title = form.querySelector("[name=title]");
    var timer = null, last = "", seq = 0;
    var esc = function (s) {
      var d = document.createElement("div");
      d.textContent = s || "";
      return d.innerHTML;
    };
    function show(data) {
      if (!data || !data.ok) { card.hidden = true; card.innerHTML = ""; return; }
      card.innerHTML =
        (data.image ? '<img src="' + esc(data.image) + '" alt="" referrerpolicy="no-referrer">' : "") +
        '<span class="text"><strong>' + esc(data.title) + "</strong><small>" + esc(data.site) + "</small></span>";
      var img = card.querySelector("img");
      if (img) img.addEventListener("error", function () { img.hidden = true; });
      card.hidden = false;
      if (title && !title.value.trim() && data.title) title.value = data.title;
      var picked = form.querySelector("[name=category]:checked");
      if (data.category && !(picked && picked.value)) {
        var radio = form.querySelector('[name=category][value="' + data.category + '"]');
        if (radio) { radio.checked = true; radio.dispatchEvent(new Event("change", { bubbles: true })); }
      }
    }
    function look() {
      var url = input.value.trim();
      if (url === last) return;
      last = url;
      if (!/^https?:\/\/\S+\.\S+/i.test(url)) { show(null); return; }
      var mine = ++seq;
      card.hidden = false;
      card.innerHTML = '<span class="text"><small>링크를 살펴보는 중…</small></span>';
      fetch(input.dataset.linkPreview + "?url=" + encodeURIComponent(url), { credentials: "same-origin", headers: { Accept: "application/json" } })
        .then(function (res) { return res.ok ? res.json() : null; })
        .catch(function () { return null; })
        .then(function (data) { if (mine === seq) show(data); }); // 늦게 온 옛 답은 버린다
    }
    input.addEventListener("input", function () { clearTimeout(timer); timer = setTimeout(look, 500); });
    input.addEventListener("paste", function () { clearTimeout(timer); timer = setTimeout(look, 50); });
    if (input.value.trim()) look(); // 고치는 화면이나 뒤로 가기로 돌아와 이미 링크가 있으면 바로 보여 준다
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

  // 되돌리기 어려운 동작은 한 번 더 확인. 브라우저 기본 창 대신 앱 디자인의 창을 쓴다.
  // data-confirm 에 물을 말, data-confirm-ok 에 확인 버튼 글자 (없으면 "지울게요").
  var confirmBox = null;
  function askConfirm(text, okLabel) {
    if (!window.HTMLDialogElement) return Promise.resolve(window.confirm(text)); // 아주 오래된 브라우저
    if (!confirmBox) {
      confirmBox = document.createElement("dialog");
      confirmBox.className = "confirm";
      confirmBox.innerHTML = '<form method="dialog"><p></p><div class="actions">' +
        '<button class="btn" value="cancel">취소</button><button class="btn ok" value="ok"></button></div></form>';
      // 바깥(어두운 곳)을 누르면 닫는다
      confirmBox.addEventListener("click", function (e) { if (e.target === confirmBox) confirmBox.close("cancel"); });
      document.body.appendChild(confirmBox);
    }
    confirmBox.querySelector("p").textContent = text;
    confirmBox.querySelector(".ok").textContent = okLabel || "지울게요";
    confirmBox.returnValue = "";
    return new Promise(function (resolve) {
      confirmBox.addEventListener("close", function () { resolve(confirmBox.returnValue === "ok"); }, { once: true });
      confirmBox.showModal();
      confirmBox.querySelector("[value=cancel]").focus(); // 실수로 Enter 를 눌러도 지워지지 않게
    });
  }
  $$("form[data-confirm]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      if (form._confirmed) { form._confirmed = false; return; }
      event.preventDefault();
      event.stopImmediatePropagation();
      var submitter = event.submitter;
      askConfirm(form.dataset.confirm, form.dataset.confirmOk).then(function (ok) {
        if (!ok) return;
        form._confirmed = true;
        if (form.requestSubmit) form.requestSubmit(submitter && submitter.form === form ? submitter : undefined);
        else { showLoaderSoon(); form.submit(); }
      });
    });
  });

  // ---------- 취향 좋아요 ----------
  // 화면을 다시 읽지 않고 하트만 바꾼다. 스크립트가 없으면 보통 폼으로 보내진다.
  $$("form[data-like]").forEach(function (form) {
    form.addEventListener("submit", function (event) {
      event.preventDefault();
      event.stopImmediatePropagation();
      var button = form.querySelector("button");
      if (button.disabled) return;
      button.disabled = true;
      fetch(form.action, {
        method: "POST",
        body: new FormData(form),
        credentials: "same-origin",
        headers: { Accept: "application/json" }
      }).then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      }).then(function (data) {
        button.classList.toggle("on", data.liked);
        button.setAttribute("aria-pressed", String(data.liked));
        form.querySelector("[data-like-text]").textContent = data.text;
        if (data.liked && !reduceMotion()) {
          button.classList.remove("pop");
          void button.offsetWidth; // 애니메이션 다시 시작
          button.classList.add("pop");
        }
      }).catch(function () {
        form.querySelector("[data-like-text]").textContent = "다시 눌러 주세요";
      }).then(function () { button.disabled = false; });
    });
  });

  // 댓글 칸: 적는 만큼 늘어나고, Enter 는 줄바꿈 (보내기는 버튼으로)
  $$("textarea[data-grow]").forEach(function (area) {
    var grow = function () {
      area.style.height = "auto";
      area.style.height = Math.min(area.scrollHeight, 160) + "px";
    };
    area.addEventListener("input", grow);
    grow();
  });

  // 안내 문구("로그인 되었습니다" 등)는 몇 초 뒤 접히며 사라진다. 누르면 바로 닫힌다.
  $$(".notice.flash").forEach(function (note, i) {
    var hide = function () {
      note.classList.add("gone");
      setTimeout(function () { note.parentNode && note.parentNode.removeChild(note); }, 400);
    };
    note.addEventListener("click", hide);
    setTimeout(hide, 4000 + i * 600);
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

  // ---------- 사진 여러 장 올리기 ----------
  // 고른 사진을 한 장씩 줄여서 따로 보낸다. 배포 서버는 요청 하나에 4.5MB까지만 받기 때문이다.
  // 찍은 날은 사진의 촬영 정보(EXIF)에서 읽는다. 줄이면 그 정보가 빠지므로 줄이기 전에 읽는다.
  function readTakenDate(file) {
    return new Promise(function (resolve) {
      if (!/^image\/jpe?g$/i.test(file.type)) return resolve(null);
      var reader = new FileReader();
      reader.onerror = function () { resolve(null); };
      reader.onload = function () {
        try { resolve(exifDate(new DataView(reader.result))); } catch (e) { resolve(null); }
      };
      reader.readAsArrayBuffer(file.slice(0, 256 * 1024));
    });
  }
  // JPEG 의 EXIF 에서 촬영일(DateTimeOriginal, 없으면 DateTime)을 "YYYY-MM-DD" 로 꺼낸다
  function exifDate(view) {
    if (view.getUint16(0) !== 0xFFD8) return null;
    var offset = 2;
    while (offset + 10 < view.byteLength) {
      var marker = view.getUint16(offset);
      if ((marker & 0xFF00) !== 0xFF00) return null;
      if (marker === 0xFFE1 && view.getUint32(offset + 4) === 0x45786966) {
        var tiff = offset + 10;
        var little = view.getUint16(tiff) === 0x4949;
        var u16 = function (o) { return view.getUint16(o, little); };
        var u32 = function (o) { return view.getUint32(o, little); };
        var find = function (dir, tag) {
          var count = u16(dir);
          for (var i = 0; i < count; i++) {
            var entry = dir + 2 + i * 12;
            if (u16(entry) === tag) return entry;
          }
          return null;
        };
        var ifd0 = tiff + u32(tiff + 4);
        var exifPointer = find(ifd0, 0x8769);
        var entry = exifPointer !== null ? find(tiff + u32(exifPointer + 8), 0x9003) : null;
        if (entry === null) entry = find(ifd0, 0x0132);
        if (entry === null) return null;
        var at = tiff + u32(entry + 8), text = "";
        for (var j = 0; j < 10; j++) text += String.fromCharCode(view.getUint8(at + j));
        var m = /^(\d{4}):(\d{2}):(\d{2})$/.exec(text);
        return m && m[1] !== "0000" ? m[1] + "-" + m[2] + "-" + m[3] : null;
      }
      offset += 2 + view.getUint16(offset + 2);
    }
    return null;
  }

  $$("form[data-batch-upload]").forEach(function (form) {
    var input = form.querySelector('input[type="file"][multiple]');
    if (!input || !window.fetch || !window.FormData) return; // 스크립트 없이 보내면 고른 사진 중 한 장만 올라간다
    var zone = form.querySelector("[data-batch-zone]");
    var list = form.querySelector("[data-batch-list]");
    var hint = form.querySelector("[data-batch-hint]");
    var progress = form.querySelector("[data-batch-progress]");
    var countText = form.querySelector("[data-batch-count]");
    var bar = form.querySelector("[data-batch-bar]");
    var submit = form.querySelector("[data-batch-submit]");
    var captionField = form.querySelector("[data-single-only]");
    var maxBytes = parseInt(input.dataset.maxBytes, 10) || Infinity;
    var maxFiles = parseInt(input.dataset.maxFiles, 10) || 30;
    var hintHtml = hint.innerHTML;
    var errorBox = document.createElement("p");
    errorBox.className = "error";
    errorBox.hidden = true;
    progress.after(errorBox);
    var items = [], running = false;

    function setState(item, state, label) {
      item.state = state;
      item.li.dataset.state = state;
      item.li.querySelector(".state").textContent = label;
    }
    // append 가 참이면 지금 목록에 덧붙인다 (드라이브에서 가져온 사진). 아니면 새로 고른 것으로 바꾼다.
    function choose(fileList, append) {
      if (running) return;
      if (!append) {
        items.forEach(function (item) { URL.revokeObjectURL(item.preview); });
        list.innerHTML = "";
        items = [];
      }
      var picked = Array.prototype.filter.call(fileList, function (f) { return f.type.indexOf("image/") === 0; });
      var room = maxFiles - items.length;
      items = items.concat(picked.slice(0, Math.max(0, room)).map(function (file) {
        var li = document.createElement("li");
        var img = document.createElement("img");
        var state = document.createElement("span");
        var item = { file: file, preview: URL.createObjectURL(file), li: li };
        img.alt = "";
        img.src = item.preview;
        state.className = "state";
        li.append(img, state);
        list.append(li);
        setState(item, "wait", "대기");
        return item;
      }));
      list.hidden = !items.length;
      if (captionField) captionField.hidden = items.length > 1; // 한마디는 한 장일 때만. 여러 장이면 올린 뒤 사진마다
      hint.innerHTML = items.length
        ? items.length + "장을 골랐어요<br><small>" + (picked.length > room ? maxFiles + "장까지만 골랐어요" : "다시 고르면 바뀌어요") + "</small>"
        : hintHtml;
      errorBox.hidden = true;
      progress.hidden = true;
      submit.textContent = "올리기";
    }
    input.addEventListener("change", function () { choose(input.files); });
    form._batchAdd = function (files) { choose(files, true); };
    form._batchRoom = function () { return running ? 0 : maxFiles - items.length; };
    form._batchHint = function (text) { hint.innerHTML = text; };
    zone.addEventListener("dragover", function () { zone.classList.add("dragging"); });
    zone.addEventListener("dragleave", function () { zone.classList.remove("dragging"); });
    zone.addEventListener("drop", function () { zone.classList.remove("dragging"); });

    form.addEventListener("submit", function (e) {
      if (!items.length) return; // 고른 사진이 없으면 서버가 "사진을 골라 주세요"라고 알려 준다
      e.preventDefault();
      if (!running) upload();
    });

    function upload() {
      var queue = items.filter(function (item) { return item.state !== "done"; });
      if (!queue.length) return;
      var base = new FormData(form);
      base.delete("image");
      var chosenDate = base.get("taken_on");
      var albumId = null, done = 0, failed = 0, stopped = false;
      running = true;
      submit.disabled = true;
      input.disabled = true;
      progress.hidden = false;
      errorBox.hidden = true;
      var tick = function () {
        countText.textContent = (done + failed) + " / " + queue.length + "장";
        bar.style.width = ((done + failed) / queue.length * 100) + "%";
      };
      var fail = function (item, message) {
        failed++;
        setState(item, "failed", "실패");
        errorBox.textContent = message;
        errorBox.hidden = false;
        if (/가득|오늘은/.test(message)) stopped = true; // 한도에 걸리면 나머지는 보내지 않는다
      };
      tick();

      (function next(i) {
        if (i >= queue.length || stopped) return finish();
        var item = queue[i];
        setState(item, "work", "준비 중");
        readTakenDate(item.file).then(function (taken) {
          return shrinkImage(item.file).then(function (ready) { return { ready: ready, taken: taken }; });
        }).then(function (r) {
          if (r.ready.size > maxBytes) return { ok: false, error: "사진이 너무 커요 (" + sizeText(r.ready.size) + "). " + sizeText(maxBytes) + " 이하로 골라 주세요." };
          var data = new FormData();
          base.forEach(function (value, key) { data.append(key, value); });
          if (albumId) { data.set("album", albumId); data.delete("new_album"); } // 새 앨범은 첫 장 때 만들어진다
          if (!chosenDate && r.taken) data.set("taken_on", r.taken);
          if (items.length > 1) data.delete("caption");
          data.append("image", r.ready, r.ready.name);
          setState(item, "work", "올리는 중");
          return fetch(form.getAttribute("action") || location.href, {
            method: "POST", body: data, credentials: "same-origin", headers: { Accept: "application/json" }
          }).then(function (res) {
            return res.json().catch(function () { return { ok: false, error: "서버가 답하지 않았어요 (" + res.status + "). 잠시 뒤 다시 해 주세요." }; });
          });
        }).then(function (result) {
          if (result.ok) {
            done++;
            setState(item, "done", "완료");
            if (result.album) albumId = String(result.album);
          } else {
            fail(item, result.error || "올리지 못했어요.");
          }
        }).catch(function () {
          fail(item, "인터넷 연결을 확인해 주세요.");
        }).then(function () {
          tick();
          next(i + 1);
        });
      })(0);

      function finish() {
        running = false;
        input.disabled = false;
        submit.disabled = false;
        if (!failed && !stopped) {
          var to = albumId ? form.dataset.albumsUrl + albumId + "/" : form.dataset.albumsUrl;
          location.href = to + "?uploaded=" + done;
          return;
        }
        countText.textContent = done + "장 올렸고, " + (queue.length - done) + "장은 못 올렸어요";
        submit.textContent = stopped ? "올리기" : "못 올린 사진 다시 올리기";
      }
    }
  });

  // ---------- 드라이브에서 골라 가져오기 ----------
  // Google Picker 로 고른 사진을 브라우저가 직접 내려받아 위의 여러 장 목록에 덧붙인다.
  // 권한은 'drive.file'(고른 파일만)이고, 토큰은 이 페이지 안에서만 쓴다. 서버에는 보내지 않는다.
  var loadScript = function (src) {
    return new Promise(function (resolve, reject) {
      var s = document.createElement("script");
      s.src = src;
      s.async = true;
      s.onload = resolve;
      s.onerror = function () { reject(new Error("load " + src)); };
      document.head.appendChild(s);
    });
  };
  var googleReady = null;
  function loadGoogle() {
    if (!googleReady) {
      googleReady = Promise.all([
        loadScript("https://accounts.google.com/gsi/client"),
        loadScript("https://apis.google.com/js/api.js").then(function () {
          return new Promise(function (resolve) { gapi.load("client:picker", resolve); });
        })
      ]);
      googleReady.catch(function () { googleReady = null; }); // 실패하면 다음에 다시 시도
    }
    return googleReady;
  }
  var DRIVE_SCOPE = "https://www.googleapis.com/auth/drive.file";
  var driveToken = null;
  function getDriveToken(clientId) {
    if (driveToken && driveToken.expires > Date.now() + 60000) return Promise.resolve(driveToken.value);
    return new Promise(function (resolve, reject) {
      var client = google.accounts.oauth2.initTokenClient({
        client_id: clientId,
        scope: DRIVE_SCOPE,
        callback: function (res) {
          if (res.error || !res.access_token) return reject(new Error(res.error || "no token"));
          driveToken = { value: res.access_token, expires: Date.now() + (res.expires_in || 3600) * 1000 };
          resolve(res.access_token);
        },
        error_callback: function (err) { reject(new Error((err && err.type) || "popup")); }
      });
      client.requestAccessToken({ prompt: driveToken ? "" : undefined });
    });
  }
  function openPicker(button, token, maxItems) {
    return new Promise(function (resolve) {
      var view = new google.picker.DocsView(google.picker.ViewId.DOCS)
        .setMimeTypes("image/jpeg,image/jpg,image/png,image/webp,image/gif,image/heic,image/heif")
        .setIncludeFolders(true)
        .setSelectFolderEnabled(false);
      new google.picker.PickerBuilder()
        .setAppId(button.dataset.appId)
        .setDeveloperKey(button.dataset.apiKey)
        .setOAuthToken(token)
        .setLocale("ko")
        .addView(view)
        .enableFeature(google.picker.Feature.MULTISELECT_ENABLED)
        .setMaxItems(maxItems)
        .setCallback(function (data) {
          var action = data[google.picker.Response.ACTION];
          if (action === google.picker.Action.PICKED) resolve(data[google.picker.Response.DOCUMENTS] || []);
          else if (action === google.picker.Action.CANCEL) resolve([]);
        })
        .build()
        .setVisible(true);
    });
  }
  // 파일 내용을 받는다. 먼저 fetch 로, 안 되면(CORS 등) Google 클라이언트 라이브러리로 받는다.
  function downloadDriveFile(doc, token) {
    var id = doc[google.picker.Document.ID];
    var name = doc[google.picker.Document.NAME] || "drive.jpg";
    var type = doc[google.picker.Document.MIME_TYPE] || "image/jpeg";
    var asFile = function (blob) { return new File([blob], name, { type: type }); };
    return fetch("https://www.googleapis.com/drive/v3/files/" + encodeURIComponent(id) + "?alt=media", {
      headers: { Authorization: "Bearer " + token }
    }).then(function (res) {
      if (!res.ok) throw new Error("HTTP " + res.status);
      return res.blob();
    }).then(asFile, function () {
      gapi.client.setToken({ access_token: token });
      return gapi.client.request({ path: "/drive/v3/files/" + encodeURIComponent(id), params: { alt: "media" } }).then(function (res) {
        var text = res.body, bytes = new Uint8Array(text.length);
        for (var i = 0; i < text.length; i++) bytes[i] = text.charCodeAt(i) & 0xff;
        return asFile(new Blob([bytes], { type: type }));
      });
    });
  }
  var googleLoaded = function () {
    return !!(window.google && google.accounts && google.accounts.oauth2 && google.picker && window.gapi && gapi.client);
  };
  $$("[data-drive-picker]").forEach(function (button) {
    var form = button.closest("form");
    // 브라우저는 탭 직후에 바로 연 창만 허락한다 (특히 아이폰 Safari).
    // 그래서 Google 라이브러리는 화면을 열 때 미리 불러 두고, 탭에서는 곧바로 권한 창을 연다.
    // 앱 안 브라우저 검사(아래)가 버튼을 숨긴 뒤에 판단하도록 한 박자 늦춘다
    setTimeout(function () { if (!button.hidden) loadGoogle().catch(function () {}); }, 0);
    button.addEventListener("click", function () {
      if (!form || !form._batchAdd) return;
      var room = form._batchRoom();
      if (room <= 0) { form._batchHint("한 번에 30장까지예요. 먼저 올린 뒤 더 가져와 주세요."); return; }
      if (!googleLoaded()) {
        form._batchHint("Google 드라이브를 준비하고 있어요. 잠시 뒤 다시 눌러 주세요.");
        loadGoogle().catch(function () { form._batchHint("Google 드라이브에 연결하지 못했어요. 인터넷 연결을 확인해 주세요."); });
        return;
      }
      button.disabled = true;
      var token;
      getDriveToken(button.dataset.clientId).then(function (t) {
        token = t;
        return openPicker(button, token, room);
      }).then(function (docs) {
        if (!docs.length) return;
        var got = [], n = 0;
        form._batchHint("드라이브에서 받는 중… 0 / " + docs.length + "장");
        // 한 장씩 차례로 받는다 (휴대폰 메모리를 아끼려고)
        return docs.reduce(function (chain, doc) {
          return chain.then(function () {
            return downloadDriveFile(doc, token).then(function (file) { got.push(file); }, function () {}).then(function () {
              n++;
              form._batchHint("드라이브에서 받는 중… " + n + " / " + docs.length + "장");
            });
          });
        }, Promise.resolve()).then(function () {
          if (got.length) form._batchAdd(got);
          if (got.length < docs.length) form._batchHint(got.length + "장을 가져왔어요<br><small>" + (docs.length - got.length) + "장은 받지 못했어요</small>");
        });
      }).catch(function (err) {
        var msg = String(err && err.message || "");
        form._batchHint(/popup|closed/.test(msg)
          ? "Google 창이 닫혔어요. 다시 눌러 주세요."
          : "Google 드라이브에 연결하지 못했어요. 잠시 뒤 다시 해 주세요.");
      }).then(function () { button.disabled = false; });
    });
  });

  // ---------- 앱 안 브라우저 ----------
  // 카카오톡·인스타그램 같은 앱 안의 브라우저에서는 Google 이 로그인을 막는다.
  // 그때는 Google 버튼을 숨기고 다른 브라우저로 열라는 안내를 보인다. 카카오 로그인은 그대로 된다.
  var ua = navigator.userAgent || "";
  var inKakao = /KAKAOTALK/i.test(ua);
  var inApp = inKakao || /Instagram|FBAN|FBAV|FB_IAB|Line\/|NAVER\(inapp|DaumApps|everytimeApp|; wv\)/i.test(ua);
  if (inApp) {
    $$("[data-needs-browser]").forEach(function (el) { el.hidden = true; });
    $$("[data-inapp-notice]").forEach(function (notice) {
      notice.hidden = false;
      var open = notice.querySelector("[data-open-external]");
      // 카카오톡은 이 주소로 바깥 브라우저를 여는 것으로 알려져 있다 (공식 문서는 없음, 안 되면 아래 안내를 따른다)
      if (open && inKakao) {
        open.hidden = false;
        open.href = "kakaotalk://web/openExternal?url=" + encodeURIComponent(location.href);
      }
    });
  }

  if ("serviceWorker" in navigator) {
    navigator.serviceWorker.register("/sw.js").catch(function () {});
  }

  // ---------- 기념일 알림 ----------
  // 우리 › 알림 화면. 이 기기의 상태를 보여 주고, 알림 받기·끄기·시험을 한다. 보내기는 서버(Cron)가 한다.
  var pushBox = document.querySelector("[data-push]");
  if (pushBox) {
    var pushMsg = pushBox.querySelector("[data-push-msg]");
    var supported = "serviceWorker" in navigator && "PushManager" in window && "Notification" in window;
    var isIOS = /iPhone|iPad|iPod/.test(ua) || (navigator.platform === "MacIntel" && navigator.maxTouchPoints > 1);
    var standalone = navigator.standalone === true || window.matchMedia("(display-mode: standalone)").matches;

    var say = function (text) {
      if (!pushMsg) return;
      pushMsg.textContent = text || "";
      pushMsg.hidden = !text;
    };
    var show = function (state) {
      $$("[data-push-state]", pushBox).forEach(function (p) { p.hidden = p.dataset.pushState !== state; });
      pushBox.querySelector("[data-push-on]").hidden = state !== "off";
      pushBox.querySelector("[data-push-off]").hidden = state !== "on";
      pushBox.querySelector("[data-push-test]").hidden = state !== "on";
    };
    // 서버의 공개 키(base64url)를 브라우저가 받는 바이트 배열로
    var keyBytes = function (base64url) {
      var b64 = (base64url + "===".slice((base64url.length + 3) % 4)).replace(/-/g, "+").replace(/_/g, "/");
      var raw = atob(b64);
      var out = new Uint8Array(raw.length);
      for (var i = 0; i < raw.length; i++) out[i] = raw.charCodeAt(i);
      return out;
    };
    var postJSON = function (url, data) {
      return fetch(url, {
        method: "POST",
        headers: { "Content-Type": "application/json", "X-CSRFToken": csrfToken() },
        credentials: "same-origin",
        body: JSON.stringify(data || {}),
      }).then(function (res) {
        if (!res.ok) throw new Error("HTTP " + res.status);
        return res.json();
      });
    };
    var registration = function () { return navigator.serviceWorker.ready; };
    var refresh = function () {
      if (!supported) return show(isIOS && !standalone ? "ios-install" : "unsupported");
      if (Notification.permission === "denied") return show("denied");
      return registration()
        .then(function (reg) { return reg.pushManager.getSubscription(); })
        .then(function (sub) {
          if (!sub) return show("off");
          // 브라우저에 구독이 있어도 서버에서 지워졌을 수 있다 (구독 교체, 저장 실패 등). 열 때마다 다시 맞춘다.
          return postJSON("/me/notifications/subscribe/", sub.toJSON())
            .then(function () { show("on"); })
            .catch(function () { show("off"); });
        })
        .catch(function () { show("unsupported"); });
    };

    pushBox.querySelector("[data-push-on]").addEventListener("click", function () {
      say("");
      // 아이폰은 누른 직후에 허용을 물어야 해서, 다른 기다림보다 먼저 묻는다
      var asked = Notification.permission === "granted" ? Promise.resolve("granted") : Notification.requestPermission();
      Promise.resolve(asked)
        .then(function (permission) {
          if (permission !== "granted") throw new Error("permission " + permission);
          return registration();
        })
        .then(function (reg) {
          return reg.pushManager.subscribe({
            userVisibleOnly: true,
            applicationServerKey: keyBytes(pushBox.dataset.publicKey),
          });
        })
        .then(function (sub) { return postJSON("/me/notifications/subscribe/", sub.toJSON()); })
        .then(refresh)
        .catch(function () {
          if (Notification.permission === "denied") return show("denied");
          say("알림을 켜지 못했어요. 잠시 뒤 다시 해 볼까요?");
          refresh();
        });
    });

    pushBox.querySelector("[data-push-off]").addEventListener("click", function () {
      say("");
      registration()
        .then(function (reg) { return reg.pushManager.getSubscription(); })
        .then(function (sub) {
          if (!sub) return null;
          return postJSON("/me/notifications/unsubscribe/", { endpoint: sub.endpoint })
            .catch(function () {})
            .then(function () { return sub.unsubscribe(); });
        })
        .then(refresh)
        .catch(refresh);
    });

    pushBox.querySelector("[data-push-test]").addEventListener("click", function () {
      say("");
      postJSON("/me/notifications/test/")
        .then(function (data) { say(data.sent ? "시험 알림을 보냈어요." : "보내지 못했어요. 잠시 뒤 다시 해 볼까요?"); })
        .catch(function () { say("보내지 못했어요. 잠시 뒤 다시 해 볼까요?"); });
    });

    refresh();
  }
})();
