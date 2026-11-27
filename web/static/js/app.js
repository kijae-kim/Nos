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

  // 추가 팝업 안(?sheet=1)에 띄운 등록 화면: 위 '뒤로' 는 팝업 닫기 (calendar-popup.js 가 받는다)
  var appEl = document.getElementById("app");
  // 팝업 밖에서(?sheet=1 주소로 바로) 열렸으면 보통 화면으로 (메뉴·아래 바가 없는 화면에 갇히지 않게)
  if (appEl && appEl.classList.contains("in-sheet") && window.parent === window) {
    var plain = new URL(location.href);
    plain.searchParams.delete("sheet");
    location.replace(plain.href);
  }
  if (appEl && appEl.classList.contains("in-sheet") && window.parent !== window) {
    // 팝업 안에서 Esc 도 닫기 (키는 부모 창으로 올라가지 않는다)
    document.addEventListener("keydown", function (e) {
      if (e.key === "Escape") window.parent.postMessage({ nos: "sheet-close" }, location.origin);
    });
    var back = document.querySelector(".bar-head > a.circle:first-child");
    if (back) {
      back.setAttribute("aria-label", "닫기");
      var use = back.querySelector("use");
      if (use) use.setAttribute("href", "#i-close");
      back.addEventListener("click", function (e) {
        e.preventDefault();
        window.parent.postMessage({ nos: "sheet-close" }, location.origin);
      });
    }
  }

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

  // 태그 바로 넣기: 누르면 일정 글 끝에 @이름 또는 #이름 이 붙는다
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

  // 촬영 위치 (사진 지도). 줄이면 사진 정보가 지워지므로 줄이기 전에 읽는다.
  // exifr 은 사진 올리기 화면에만 실린다 (JPEG·HEIC). 못 읽거나 3초 넘게 걸리면 위치 없이 올린다.
  function readLocation(file) {
    if (!window.exifr || !file) return Promise.resolve(null);
    var timeout = new Promise(function (resolve) { setTimeout(function () { resolve(null); }, 3000); });
    var read = window.exifr.gps(file).then(function (gps) {
      if (!gps || typeof gps.latitude !== "number" || typeof gps.longitude !== "number") return null;
      return { lat: gps.latitude, lng: gps.longitude };
    }).catch(function () { return null; });
    return Promise.race([read, timeout]);
  }
  // 폼의 숨은 위치 칸에 넣는다 (한 장씩 고치는 사진 칸)
  function setLocationFields(form, loc) {
    if (!form) return;
    var lat = form.querySelector('input[name="latitude"]'), lng = form.querySelector('input[name="longitude"]');
    if (!lat || !lng) return;
    lat.value = loc ? String(loc.lat) : "";
    lng.value = loc ? String(loc.lng) : "";
  }

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
      readLocation(file).then(function (loc) {
        setLocationFields(form, loc);
        return shrinkImage(file);
      }).then(function (ready) {
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
    function show(data) {
      if (!data || !data.ok) { card.hidden = true; card.innerHTML = ""; return; }
      // 외부 사이트가 준 값이라 문자열 HTML 로 붙이지 않고 요소로 만든다 (사진 주소의 따옴표로 스크립트를 끼워 넣지 못하게)
      card.innerHTML = "";
      if (data.image && /^https:\/\//.test(data.image)) {
        var img = document.createElement("img");
        img.alt = "";
        img.referrerPolicy = "no-referrer";
        img.addEventListener("error", function () { img.hidden = true; });
        img.src = data.image;
        card.appendChild(img);
      }
      var text = document.createElement("span");
      text.className = "text";
      var strong = document.createElement("strong");
      strong.textContent = data.title || "";
      var small = document.createElement("small");
      small.textContent = data.site || "";
      text.append(strong, small);
      card.appendChild(text);
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
    confirmBox.querySelector(".ok").textContent = okLabel || "삭제할게요";
    confirmBox.returnValue = "";
    return new Promise(function (resolve) {
      confirmBox.addEventListener("close", function () { resolve(confirmBox.returnValue === "ok"); }, { once: true });
      confirmBox.showModal();
      confirmBox.querySelector("[value=cancel]").focus(); // 실수로 Enter 를 눌러도 지워지지 않게
    });
  }
  // 문서에 한 번 걸어 둔다 (사진 넘기기처럼 나중에 바꿔 끼운 폼도 묻게). 잡는 단계라 폼의 다른 처리보다 먼저 돈다.
  document.addEventListener("submit", function (event) {
      var form = event.target;
      if (!form.matches || !form.matches("form[data-confirm]")) return;
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
  }, true);

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
  // 끝나는 날(여러 날 일정)을 넣으면 하루 종일로 고정한다 (서버도 같은 규칙)
  var endDate = document.querySelector("[data-end-date]");
  var startDate = document.getElementById("id_date");
  if (allDay && timeFields) {
    var syncAllDay = function () {
      var multi = !!(endDate && endDate.value && startDate && endDate.value !== startDate.value);
      if (multi) allDay.checked = true;
      allDay.disabled = multi; // 여러 날이면 끌 수 없다 (지난 일정 잠금은 fieldset 이 따로 한다)
      timeFields.hidden = allDay.checked;
    };
    allDay.addEventListener("change", syncAllDay);
    if (endDate) endDate.addEventListener("change", syncAllDay);
    if (startDate) startDate.addEventListener("change", syncAllDay);
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

  // ---------- 앱처럼 쓰기 (홈 화면에 추가) ----------
  // 홈 화면 앱으로 열려 있으면 버튼을 숨긴다. 안드로이드 크롬은 브라우저가 주는 설치 창을 바로 열고,
  // 아이폰처럼 설치 창이 없는 곳은 '공유 → 홈 화면에 추가' 안내 판을 연다
  (function () {
    var standalone = window.matchMedia("(display-mode: standalone)").matches || window.navigator.standalone === true;
    var cards = $$("[data-install]");
    if (!cards.length || standalone) return;
    var deferred = null;
    window.addEventListener("beforeinstallprompt", function (e) { e.preventDefault(); deferred = e; });
    window.addEventListener("appinstalled", function () { cards.forEach(function (c) { c.hidden = true; }); });
    cards.forEach(function (c) { c.hidden = false; });
    var guide = document.querySelector("[data-install-guide]");
    var ua = navigator.userAgent || "";
    var inAppBrowser = /KAKAOTALK|Instagram|FBAN|FBAV|FB_IAB|Line\/|NAVER\(inapp|DaumApps|; wv\)/i.test(ua);
    var apple = /iPhone|iPad|iPod/i.test(ua) || (/Macintosh/.test(ua) && navigator.maxTouchPoints > 1);
    function openGuide() {
      if (!guide) return;
      var ios = guide.querySelector('[data-install-steps="ios"]');
      var android = guide.querySelector('[data-install-steps="android"]');
      var inapp = guide.querySelector("[data-install-inapp]");
      if (inapp) inapp.hidden = !inAppBrowser;
      if (ios) ios.hidden = inAppBrowser || !apple;
      if (android) android.hidden = inAppBrowser || apple;
      if (typeof guide.showModal === "function") guide.showModal(); else guide.setAttribute("open", "");
    }
    $$("[data-install-open]").forEach(function (b) {
      b.addEventListener("click", function (e) {
        e.preventDefault();
        if (deferred) {
          var p = deferred;
          deferred = null;
          p.prompt();
          p.userChoice.then(function (choice) {
            if (choice && choice.outcome === "accepted") cards.forEach(function (c) { c.hidden = true; });
          });
        } else openGuide();
      });
    });
    if (guide) {
      var close = guide.querySelector("[data-install-close]");
      if (close) close.addEventListener("click", function () { guide.close(); });
      guide.addEventListener("click", function (e) { if (e.target === guide) guide.close(); });
    }
  })();

  // ---------- 처음 한 번 튜토리얼 · 업데이트 소식 ----------
  // 둘 다 dialog 안의 form 이 끝났다고 서버에 알린다 (CSRF 토큰은 form 안). 시작 화면이 끝난 뒤에 연다
  function afterSplash(fn) {
    if (!root.classList.contains("splash-on")) return fn();
    var t = setInterval(function () { if (!root.classList.contains("splash-on")) { clearInterval(t); fn(); } }, 250);
  }
  function tellServer(form) {
    try { fetch(form.action, { method: "POST", body: new FormData(form), credentials: "same-origin", keepalive: true }); } catch (e) { /* 다음에 다시 뜬다 */ }
  }
  function openDialog(d) { if (typeof d.showModal === "function") d.showModal(); else d.setAttribute("open", ""); }
  (function () {
    var dlg = document.querySelector("[data-tutorial]");
    if (!dlg) return;
    var form = dlg.querySelector("[data-tutorial-form]");
    var track = dlg.querySelector("[data-tutorial-track]");
    var slides = $$(".tutorial-slide", dlg);
    var dots = $$(".tutorial-dots i", dlg);
    var next = dlg.querySelector("[data-tutorial-next]");
    var told = false;
    function index() { return Math.round(track.scrollLeft / Math.max(1, track.clientWidth)); }
    function sync() {
      var i = index();
      dots.forEach(function (d, k) { d.classList.toggle("on", k === i); });
      next.textContent = i >= slides.length - 1 ? "시작하기" : "다음";
    }
    function finish() {
      if (!told) { told = true; tellServer(form); }
      if (dlg.open) dlg.close();
    }
    track.addEventListener("scroll", function () { window.requestAnimationFrame(sync); }, { passive: true });
    next.addEventListener("click", function () {
      var i = index();
      if (i >= slides.length - 1) return finish();
      track.scrollTo({ left: (i + 1) * track.clientWidth, behavior: "smooth" });
    });
    form.addEventListener("submit", function (e) { e.preventDefault(); finish(); }); // 건너뛰기
    dlg.addEventListener("cancel", function () { finish(); }); // Esc
    $$("[data-tutorial-replay]").forEach(function (b) {
      b.addEventListener("click", function () { track.scrollLeft = 0; sync(); openDialog(dlg); });
    });
    sync();
    if (dlg.hasAttribute("data-auto")) afterSplash(function () { openDialog(dlg); });
  })();
  (function () {
    var dlg = document.querySelector("[data-news-popup]");
    if (!dlg) return;
    var form = dlg.querySelector("[data-news-form]");
    var told = false;
    function done() { if (!told) { told = true; tellServer(form); } }
    form.addEventListener("submit", function (e) { e.preventDefault(); done(); dlg.close(); });
    dlg.addEventListener("close", done);
    dlg.querySelector("a[href]").addEventListener("click", done); // 지난 소식 보기로 가도 본 것으로
    afterSplash(function () { openDialog(dlg); });
  })();

  // ---------- 사진 옆으로 넘겨 보기 ----------
  // 손가락을 따라 사진이 움직이고, 충분히 밀면 앞·뒤 사진으로. 화면을 다시 받지 않는다:
  // 앞뒤 사진은 미리 받아 두고(같은 서명 주소라야 다시 안 받는다) 바로 바꿔 끼우고,
  // 아래 정보(한마디·앨범·수정 버튼)만 그 사진 화면에서 받아 바꾼다. 주소는 바꾸되 기록은 쌓지 않아 '뒤로'는 연 곳으로.
  (function () {
    var view = document.querySelector("[data-photo-swipe]");
    var stripEl = document.getElementById("photo-strip");
    if (!view || !stripEl) return;
    var img = view.querySelector("img");
    var body = document.querySelector("[data-photo-body]");
    var posEl = document.querySelector("[data-photo-pos]");
    var navPrev = view.querySelector(".photo-nav.prev"), navNext = view.querySelector(".photo-nav.next");
    var cache = {}; // 화면 주소 → { page, prev, next, pos, src, thumb, img, doc }
    var learn = function (items) {
      items.forEach(function (it) { if (!cache[it.page]) cache[it.page] = it; });
    };
    try { learn(JSON.parse(stripEl.textContent)); } catch (e) { return; }
    var current = cache[location.pathname + location.search];
    if (!current) return;
    current.img = img; // 지금 사진은 이미 받았다
    var loadDoc = function (c) {
      if (c.doc) return c.doc;
      c.doc = fetch(c.page, { credentials: "same-origin" })
        .then(function (r) { if (!r.ok) throw new Error(r.status); return r.text(); })
        .then(function (t) {
          var doc = new DOMParser().parseFromString(t, "text/html");
          var s = doc.getElementById("photo-strip");
          if (s) learn(JSON.parse(s.textContent));
          return doc;
        });
      c.doc.catch(function () { c.doc = null; });
      return c.doc;
    };
    // 앞뒤 한 장씩 사진과 정보를 미리 받는다
    var warm = function (c) {
      [c.prev, c.next].forEach(function (u) {
        var n = u && cache[u];
        if (!n) return;
        if (!n.img) { n.img = new Image(); n.img.decoding = "async"; n.img.src = n.src; }
        loadDoc(n).catch(function () {});
      });
    };
    var show = function (c, dir) {
      current = c;
      // 다 받은 사진은 바로, 아직이면 작은 사진을 먼저 보여 주고 다 받으면 바꾼다
      var ready = c.img && c.img.complete && c.img.naturalWidth;
      img.src = ready ? c.src : c.thumb;
      if (!ready) {
        if (!c.img) { c.img = new Image(); c.img.src = c.src; }
        c.img.addEventListener("load", function () { if (current === c) img.src = c.src; }, { once: true });
      }
      // 반대쪽에서 들어온다
      img.style.transition = "none";
      img.style.transform = "translateX(" + (dir * 30) + "%)";
      void img.offsetWidth;
      img.style.transition = "transform .2s ease, opacity .2s ease";
      img.style.transform = "";
      img.style.opacity = "1";
      view.dataset.prev = c.prev || "";
      view.dataset.next = c.next || "";
      if (navPrev) { navPrev.hidden = !c.prev; navPrev.setAttribute("href", c.prev || ""); }
      if (navNext) { navNext.hidden = !c.next; navNext.setAttribute("href", c.next || ""); }
      if (posEl) posEl.textContent = c.pos;
      try { history.replaceState(history.state, "", c.page); } catch (e) {}
      body.style.opacity = ".4";
      loadDoc(c).then(function (doc) {
        if (current !== c) return;
        var nb = doc.querySelector("[data-photo-body]");
        if (nb) body.innerHTML = nb.innerHTML;
        var ni = doc.querySelector("[data-photo-swipe] img");
        if (ni) img.alt = ni.alt;
        body.style.opacity = "";
        warm(c);
      }, function () { location.replace(c.page); }); // 못 받으면 화면째로
      warm(c);
    };
    var busy = false;
    var go = function (url, dir) {
      if (!url) { img.style.transform = ""; return; }
      var c = cache[url];
      if (!c) { location.replace(url); return; }
      if (busy) return;
      busy = true;
      img.style.transition = "transform .15s ease, opacity .15s ease";
      img.style.transform = "translateX(" + (dir * -40) + "%)";
      img.style.opacity = "0";
      setTimeout(function () { busy = false; show(c, dir); }, 150);
    };
    // 한 시간이 지나 서명 주소가 끝나면 화면째로 다시 받는다
    img.addEventListener("error", function () { location.replace(current.page); });
    warm(current);
    var start = null;
    view.addEventListener("touchstart", function (e) {
      if (e.touches.length !== 1) { start = null; return; }
      start = { x: e.touches[0].clientX, y: e.touches[0].clientY, dx: 0, horizontal: null };
      img.style.transition = "none";
    }, { passive: true });
    view.addEventListener("touchmove", function (e) {
      if (!start) return;
      var dx = e.touches[0].clientX - start.x, dy = e.touches[0].clientY - start.y;
      if (start.horizontal === null && Math.abs(dx) + Math.abs(dy) > 8) start.horizontal = Math.abs(dx) > Math.abs(dy);
      if (!start.horizontal) return; // 위아래로 미는 건 화면 스크롤
      e.preventDefault();
      // 끝에 다다르면 덜 움직이게
      var edge = (dx > 0 && !view.dataset.prev) || (dx < 0 && !view.dataset.next);
      start.dx = edge ? dx / 4 : dx;
      img.style.transform = "translateX(" + start.dx + "px)";
    }, { passive: false });
    view.addEventListener("touchend", function () {
      if (!start) return;
      var dx = start.dx;
      start = null;
      img.style.transition = "transform .2s ease";
      if (dx < -60 && view.dataset.next) go(view.dataset.next, 1);
      else if (dx > 60 && view.dataset.prev) go(view.dataset.prev, -1);
      else img.style.transform = "";
    });
    document.addEventListener("keydown", function (e) {
      if (e.target.closest && e.target.closest("input, textarea, [contenteditable]")) return;
      if (e.key === "ArrowRight" && view.dataset.next) go(view.dataset.next, 1);
      if (e.key === "ArrowLeft" && view.dataset.prev) go(view.dataset.prev, -1);
    });
    [navPrev, navNext].forEach(function (a) {
      if (a) a.addEventListener("click", function (e) { e.preventDefault(); go(a.getAttribute("href"), a === navNext ? 1 : -1); });
    });
  })();

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
        Promise.all([readTakenDate(item.file), readLocation(item.file)]).then(function (meta) {
          return shrinkImage(item.file).then(function (ready) { return { ready: ready, taken: meta[0], loc: meta[1] }; });
        }).then(function (r) {
          if (r.ready.size > maxBytes) return { ok: false, error: "사진이 너무 커요 (" + sizeText(r.ready.size) + "). " + sizeText(maxBytes) + " 이하로 골라 주세요." };
          var data = new FormData();
          base.forEach(function (value, key) { data.append(key, value); });
          if (albumId) { data.set("album", albumId); data.delete("new_album"); } // 새 앨범은 첫 장 때 만들어진다
          if (!chosenDate && r.taken) data.set("taken_on", r.taken);
          data.set("latitude", r.loc ? String(r.loc.lat) : "");
          data.set("longitude", r.loc ? String(r.loc.lng) : "");
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

  // ---------- 프로필 수정 ----------
  // 사진은 동그라미에 맞춘 정사각형 JPEG 로 보낸다 (서버가 256px 로 다시 줄이고 촬영 정보를 지운다).
  var avatarInput = document.querySelector("[data-avatar-input]");
  if (avatarInput) {
    var face = document.querySelector("[data-preview-face]");
    var photoPreview = document.querySelector("[data-preview-photo]");
    var emojiInput = document.querySelector("[data-emoji-input]");
    var removePhoto = document.querySelector("[data-remove-photo]");
    var showFace = function () {
      var hasPhoto = photoPreview && !photoPreview.hidden;
      face.hidden = !!hasPhoto;
      face.textContent = emojiInput.value;
      face.classList.toggle("emoji", !!emojiInput.value);
    };
    // 사진을 줄이는 동안에는 저장을 막는다 (원본이 그대로 가면 "너무 커요" 가 될 수 있다)
    var submitBtn = document.querySelector("[data-profile-submit]");
    var busy = function (on) {
      if (!submitBtn) return;
      submitBtn.disabled = on;
      submitBtn.textContent = on ? "사진을 준비하고 있어요…" : "저장";
    };
    // 고른 사진을 동그라미에 맞춘다: 끌어서 옮기기, 막대·두 손가락·휠로 키우기 → 그 부분만 512px JPEG 로
    var sheet = document.querySelector("[data-crop-sheet]");
    var stage = sheet.querySelector("[data-crop-stage]");
    var cropImg = sheet.querySelector("[data-crop-img]");
    var zoomInput = sheet.querySelector("[data-crop-zoom]");
    var crop = null; // { url, w, h, zoom, x, y } — x·y 는 가운데에서 옮긴 거리(px)
    var stageSize = function () { return stage.clientWidth || 280; };
    var layout = function () {
      var S = stageSize();
      var s = S / Math.min(crop.w, crop.h) * crop.zoom; // 동그라미를 늘 꽉 채우는 배율
      var dw = crop.w * s, dh = crop.h * s;
      // 사진 밖 빈 곳이 동그라미에 들어오지 않게
      var mx = (dw - S) / 2, my = (dh - S) / 2;
      crop.x = Math.max(-mx, Math.min(mx, crop.x));
      crop.y = Math.max(-my, Math.min(my, crop.y));
      crop.s = s;
      crop.left = (S - dw) / 2 + crop.x;
      crop.top = (S - dh) / 2 + crop.y;
      cropImg.style.width = dw + "px";
      cropImg.style.height = dh + "px";
      cropImg.style.transform = "translate(" + crop.left + "px," + crop.top + "px)";
    };
    var setZoom = function (z) {
      crop.zoom = Math.max(1, Math.min(4, z));
      zoomInput.value = crop.zoom;
      layout();
    };
    var closeCrop = function () {
      if (crop) URL.revokeObjectURL(crop.url);
      crop = null;
      if (sheet.open) sheet.close();
    };
    var pointers = {}, drag = null;
    var pinchDist = function () {
      var p = Object.keys(pointers).map(function (k) { return pointers[k]; });
      return Math.hypot(p[0].x - p[1].x, p[0].y - p[1].y);
    };
    stage.addEventListener("pointerdown", function (e) {
      if (!crop) return;
      stage.setPointerCapture(e.pointerId);
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      var n = Object.keys(pointers).length;
      if (n === 1) drag = { x: e.clientX, y: e.clientY, ox: crop.x, oy: crop.y };
      if (n === 2) drag = { pinch: pinchDist(), zoom: crop.zoom };
    });
    stage.addEventListener("pointermove", function (e) {
      if (!crop || !pointers[e.pointerId]) return;
      pointers[e.pointerId] = { x: e.clientX, y: e.clientY };
      if (drag && drag.pinch) setZoom(drag.zoom * pinchDist() / drag.pinch);
      else if (drag) { crop.x = drag.ox + e.clientX - drag.x; crop.y = drag.oy + e.clientY - drag.y; layout(); }
    });
    var lift = function (e) {
      delete pointers[e.pointerId];
      var rest = Object.keys(pointers);
      // 두 손가락 중 하나를 떼면 남은 손가락으로 이어서 옮긴다
      drag = rest.length === 1 && crop ? { x: pointers[rest[0]].x, y: pointers[rest[0]].y, ox: crop.x, oy: crop.y } : null;
    };
    stage.addEventListener("pointerup", lift);
    stage.addEventListener("pointercancel", lift);
    stage.addEventListener("wheel", function (e) {
      if (!crop) return;
      e.preventDefault();
      setZoom(crop.zoom * (e.deltaY < 0 ? 1.08 : 1 / 1.08));
    }, { passive: false });
    zoomInput.addEventListener("input", function () { if (crop) setZoom(parseFloat(zoomInput.value)); });
    sheet.querySelector("[data-crop-cancel]").addEventListener("click", function () {
      avatarInput.value = ""; // 고르지 않은 것으로 (지금 사진 그대로)
      closeCrop();
    });
    sheet.addEventListener("cancel", function () { avatarInput.value = ""; crop && URL.revokeObjectURL(crop.url); crop = null; });
    sheet.querySelector("[data-crop-ok]").addEventListener("click", function () {
      if (!crop) return;
      var OUT = 512, S = stageSize();
      var canvas = document.createElement("canvas");
      canvas.width = canvas.height = OUT;
      var ctx = canvas.getContext("2d");
      ctx.fillStyle = "#fff";
      ctx.fillRect(0, 0, OUT, OUT);
      // 화면의 동그라미(정사각형 칸)에 보이는 부분 = 원본의 이 칸
      ctx.drawImage(cropImg, -crop.left / crop.s, -crop.top / crop.s, S / crop.s, S / crop.s, 0, 0, OUT, OUT);
      closeCrop();
      busy(true);
      canvas.toBlob(function (blob) {
        busy(false);
        if (!blob) return;
        try {
          var dt = new DataTransfer();
          dt.items.add(new File([blob], "avatar.jpg", { type: "image/jpeg" }));
          avatarInput.files = dt.files; // 맞춘 사진으로 바꿔 보낸다
        } catch (err) { /* 바꿀 수 없는 브라우저는 원본을 보내고 서버가 가운데를 자른다 */ }
        if (!photoPreview) {
          photoPreview = document.createElement("img");
          photoPreview.className = "av big";
          photoPreview.alt = "";
          face.parentNode.insertBefore(photoPreview, face);
        }
        photoPreview.src = canvas.toDataURL("image/jpeg", 0.85);
        photoPreview.hidden = false;
        if (removePhoto) removePhoto.checked = false;
        showFace();
      }, "image/jpeg", 0.88);
    });
    avatarInput.addEventListener("change", function () {
      var file = avatarInput.files && avatarInput.files[0];
      if (!file) return;
      if (crop) closeCrop();
      busy(true);
      var url = URL.createObjectURL(file);
      cropImg.onload = function () {
        busy(false);
        crop = { url: url, w: cropImg.naturalWidth, h: cropImg.naturalHeight, zoom: 1, x: 0, y: 0 };
        zoomInput.value = 1;
        sheet.showModal();
        layout();
      };
      cropImg.onerror = function () { URL.revokeObjectURL(url); busy(false); }; // 못 읽는 사진(HEIC 등)은 그대로 보내 서버가 판단
      cropImg.src = url;
    });
    document.querySelectorAll("[data-emoji]").forEach(function (b) {
      b.addEventListener("click", function () { emojiInput.value = b.dataset.emoji; showFace(); });
    });
    emojiInput.addEventListener("input", showFace);
    var clear = document.querySelector("[data-emoji-clear]");
    if (clear) clear.addEventListener("click", function () { emojiInput.value = ""; showFace(); });
    if (removePhoto) removePhoto.addEventListener("change", function () {
      if (photoPreview) photoPreview.hidden = removePhoto.checked;
      showFace();
    });
    document.querySelectorAll("[data-color-pick]").forEach(function (r) {
      r.addEventListener("change", function () { face.style.setProperty("--c", "var(--" + r.value + ")"); });
    });
  }

  // ---------- 펼치기 버튼 (aria-controls 가 가리키는 칸을 열고 닫는다) ----------
  document.querySelectorAll("[data-expand][aria-controls]").forEach(function (b) {
    var box = document.getElementById(b.getAttribute("aria-controls"));
    if (!box) return;
    b.addEventListener("click", function () {
      var open = b.getAttribute("aria-expanded") !== "true";
      b.setAttribute("aria-expanded", open ? "true" : "false");
      box.hidden = !open;
    });
  });
})();
