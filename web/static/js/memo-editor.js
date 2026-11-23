// 메모 쓰기 칸 (아이폰 메모장처럼): 줄마다 <div class="ln">, 체크 줄은 <div class="ln todo [on]"> (전역 .check 와 겹치지 않게 todo).
// 체크 동그라미는 줄 왼쪽 여백에 CSS 로 그리고, 그 자리를 누르면 체크한다 (편집 불가 요소를 넣지 않아 커서가 안정적).
// 엔터·줄 앞 지우기·붙여 넣기·체크 줄 바꾸기는 줄 목록으로 바꿔 계산한 뒤 다시 그린다. 보통 글자 입력은 브라우저에 맡긴다.
(function () {
  "use strict";
  var editor = document.querySelector("[data-memo-editor]");
  var dataEl = document.getElementById("memo-data");
  if (!editor || !dataEl) return;
  var status = document.querySelector("[data-memo-status]");
  var conflictBox = document.querySelector("[data-memo-conflict]");
  var data = JSON.parse(dataEl.textContent);
  var version = data.version;
  var TICK = 30; // 줄 왼쪽에서 이 폭 안을 누르면 체크

  // ---------- 줄 목록 ↔ 화면 ----------
  function lineEl(line) {
    var div = document.createElement("div");
    div.className = "ln" + (line.t === "check" ? " todo" + (line.on ? " on" : "") : "");
    if (line.s) div.textContent = line.s; else div.appendChild(document.createElement("br"));
    return div;
  }
  function render(lines) {
    editor.innerHTML = "";
    (lines.length ? lines : [{ t: "text", on: false, s: "" }]).forEach(function (l) { editor.appendChild(lineEl(l)); });
  }
  // 브라우저가 만든 글 조각·span·겹친 div 를 줄 목록으로 정리해서 읽는다
  function serialize() {
    var lines = [];
    editor.childNodes.forEach(function (node) {
      if (node.nodeType === 3) {
        if (node.textContent) lines.push({ t: "text", on: false, s: node.textContent.replace(/\n/g, " ") });
        return;
      }
      if (node.nodeType !== 1) return;
      var check = node.classList && node.classList.contains("todo");
      var text = (node.innerText || node.textContent || "").replace(/\n+$/, "");
      // 한 div 안에 줄바꿈이 생겼으면(겹친 div·br) 여러 줄로 나눈다
      text.split("\n").forEach(function (part, i) {
        lines.push({ t: check ? "check" : "text", on: check && i === 0 ? node.classList.contains("on") : false, s: part });
      });
    });
    return lines.length ? lines : [{ t: "text", on: false, s: "" }];
  }

  // ---------- 커서 (몇 번째 줄, 줄 안 몇 번째 글자) ----------
  function topLine(node) {
    while (node && node.parentNode !== editor) node = node.parentNode;
    return node;
  }
  function caret() {
    var sel = window.getSelection();
    if (!sel.rangeCount || !editor.contains(sel.anchorNode)) return null;
    var line = topLine(sel.anchorNode);
    if (!line) return null;
    var idx = Array.prototype.indexOf.call(editor.childNodes, line);
    var r = document.createRange();
    r.selectNodeContents(line);
    r.setEnd(sel.anchorNode, sel.anchorOffset);
    return { line: idx, offset: r.toString().length, collapsed: sel.isCollapsed };
  }
  function setCaret(lineIdx, offset) {
    var line = editor.childNodes[Math.max(0, Math.min(lineIdx, editor.childNodes.length - 1))];
    if (!line) return;
    var range = document.createRange();
    var text = line.firstChild && line.firstChild.nodeType === 3 ? line.firstChild : null;
    if (text) range.setStart(text, Math.min(offset, text.length)); else range.setStart(line, 0);
    range.collapse(true);
    var sel = window.getSelection();
    sel.removeAllRanges();
    sel.addRange(range);
  }

  // ---------- 고치기 ----------
  function changed() { dirty = true; editedHere = true; keepDraft(); schedule(); }
  // 글을 고른 채로 엔터·붙여 넣기를 하면 고른 글을 먼저 지운다 (바꾸기)
  function dropSelection() {
    var sel = window.getSelection();
    if (!sel.rangeCount || sel.isCollapsed || !editor.contains(sel.anchorNode)) return;
    sel.getRangeAt(0).deleteContents();
    sel.collapseToStart();
    var c = caret();
    render(serialize());
    if (c) setCaret(c.line, c.offset);
  }
  function splitAtCaret() {
    dropSelection();
    var c = caret();
    if (!c) return;
    var lines = serialize();
    var cur = lines[c.line];
    if (cur.t === "check" && !cur.s.trim()) { // 빈 체크 줄에서 엔터 → 글 줄로 (아이폰처럼)
      cur.t = "text"; cur.on = false;
      render(lines); setCaret(c.line, 0); changed();
      return;
    }
    var after = { t: cur.t, on: false, s: cur.s.slice(c.offset) };
    cur.s = cur.s.slice(0, c.offset);
    lines.splice(c.line + 1, 0, after);
    render(lines); setCaret(c.line + 1, 0); changed();
  }
  function toggleCheckLine() {
    var c = caret();
    var lines = serialize();
    if (!c) { // 커서가 없으면 끝에 체크 줄을 하나 더해 거기서 쓴다
      lines.push({ t: "check", on: false, s: "" });
      render(lines); editor.focus(); setCaret(lines.length - 1, 0); changed();
      return;
    }
    var cur = lines[c.line];
    cur.t = cur.t === "check" ? "text" : "check";
    cur.on = false;
    render(lines); setCaret(c.line, c.offset); changed();
  }
  function pasteText(text) {
    dropSelection();
    var c = caret();
    var lines = serialize();
    if (!c) { c = { line: lines.length - 1, offset: lines[lines.length - 1].s.length }; }
    var parts = text.replace(/\r/g, "").split("\n");
    var cur = lines[c.line];
    var tail = cur.s.slice(c.offset);
    cur.s = cur.s.slice(0, c.offset) + parts[0];
    var added = parts.slice(1).map(function (p) { return { t: cur.t, on: false, s: p }; });
    var last = added.length ? added[added.length - 1] : cur;
    var endOffset = last.s.length;
    last.s += tail;
    Array.prototype.splice.apply(lines, [c.line + 1, 0].concat(added));
    render(lines); setCaret(c.line + added.length, endOffset); changed();
  }

  // 한글 입력(조합) 중에는 다시 그리지 않는다. 조합 중 엔터는 조합이 끝난 뒤 줄을 나눈다
  var composing = false, pendingSplit = false;
  editor.addEventListener("compositionstart", function () { composing = true; });
  editor.addEventListener("compositionend", function () {
    composing = false;
    setTimeout(function () {
      if (pendingSplit) { pendingSplit = false; splitAtCaret(); } else { tidy(); shortcut(); }
    }, 0);
  });
  editor.addEventListener("beforeinput", function (e) {
    if (e.inputType === "insertParagraph" || e.inputType === "insertLineBreak") {
      e.preventDefault();
      if (e.isComposing || composing) { pendingSplit = true; return; }
      splitAtCaret();
    } else if (e.inputType === "deleteContentBackward") {
      var c = caret();
      var line = c && editor.childNodes[c.line];
      // 체크 줄 맨 앞에서 지우면 글 줄로 (아이폰처럼)
      if (c && c.collapsed && c.offset === 0 && line && line.classList && line.classList.contains("todo")) {
        e.preventDefault();
        line.classList.remove("todo", "on");
        changed();
      }
    }
  });
  editor.addEventListener("paste", function (e) {
    e.preventDefault(); // 서식·스크립트 없이 글만
    pasteText((e.clipboardData || window.clipboardData).getData("text/plain") || "");
  });
  editor.addEventListener("drop", function (e) { e.preventDefault(); });
  // 줄 밖 글·겹친 줄이 생기면 정리 (커서 자리 유지)
  function tidy() {
    var messy = Array.prototype.some.call(editor.childNodes, function (n) {
      return n.nodeType === 3 || (n.nodeType === 1 && (!n.classList.contains("ln") || n.querySelector("div,p,span,b,i,font")));
    });
    if (messy || !editor.childNodes.length) {
      var c = caret();
      render(serialize());
      if (c) setCaret(c.line, c.offset);
    }
  }
  // 글 줄 맨 앞에 "- " 나 "/todo " 를 치면 체크 줄로 (띄어쓰기까지 쳐야 바뀐다: "-5도" 는 그대로)
  var SHORTCUTS = ["- ", "/todo "];
  function shortcut() {
    var c = caret();
    var el = c && c.collapsed && editor.childNodes[c.line];
    if (!el || !el.classList || el.classList.contains("todo")) return false;
    var text = el.textContent.replace(/\u00a0/g, " "); // 브라우저는 끝 띄어쓰기를 nbsp 로 넣는다
    var hit = SHORTCUTS.filter(function (p) { return c.offset === p.length && text.slice(0, p.length) === p; })[0];
    if (!hit) return false;
    var lines = serialize();
    lines[c.line] = { t: "check", on: false, s: lines[c.line].s.slice(hit.length) };
    render(lines); setCaret(c.line, 0);
    return true;
  }
  editor.addEventListener("input", function (e) {
    if (!(e.isComposing || composing)) { tidy(); shortcut(); }
    changed();
  });
  // 줄 왼쪽 동그라미를 누르면 체크 (커서는 옮기지 않는다). 마우스는 mousedown, 터치는 touchend 에서
  function tickAt(target, x) {
    var line = target.closest && target.closest(".ln.todo");
    if (!line || x - line.getBoundingClientRect().left > TICK) return null;
    return line;
  }
  editor.addEventListener("mousedown", function (e) {
    var line = tickAt(e.target, e.clientX);
    if (!line) return;
    e.preventDefault();
    line.classList.toggle("on");
    changed();
  });
  var touchFrom = null; // 손가락이 움직였으면(스크롤) 체크하지 않는다
  editor.addEventListener("touchstart", function (e) {
    var t = e.touches && e.touches[0];
    touchFrom = t ? { x: t.clientX, y: t.clientY, at: Date.now() } : null;
  }, { passive: true });
  editor.addEventListener("touchend", function (e) {
    var t = e.changedTouches && e.changedTouches[0];
    if (!t || !touchFrom || Math.abs(t.clientX - touchFrom.x) > 10 || Math.abs(t.clientY - touchFrom.y) > 10 || Date.now() - touchFrom.at > 600) return;
    var line = tickAt(e.target, t.clientX);
    if (!line) return;
    e.preventDefault(); // 이어지는 클릭·커서 옮기기·자판 열기를 막는다
    line.classList.toggle("on");
    changed();
  }, { passive: false });
  // 키보드: Ctrl(⌘)+Enter 로 지금 체크 줄 체크
  editor.addEventListener("keydown", function (e) {
    if (e.key === "Enter" && (e.metaKey || e.ctrlKey)) {
      e.preventDefault();
      var c = caret();
      var line = c && editor.childNodes[c.line];
      if (line && line.classList && line.classList.contains("todo")) { line.classList.toggle("on"); changed(); }
    }
  });

  var makeCheck = document.querySelector("[data-make-check]");
  if (makeCheck) {
    makeCheck.addEventListener("mousedown", function (e) { e.preventDefault(); }); // 쓰기 칸의 커서를 잃지 않게
    makeCheck.addEventListener("click", toggleCheckLine);
  }
  var done = document.querySelector("[data-done]");
  if (done) done.addEventListener("click", function () { editor.blur(); saveNow(); });

  // ---------- 저장 (고친 뒤 0.8초, 떠날 때) ----------
  var dirty = false, saving = false, again = false, timer = null;
  function csrf() {
    var m = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/);
    return m ? decodeURIComponent(m[1]) : "";
  }
  function show(text) { if (status) status.textContent = text; }
  function schedule() { clearTimeout(timer); timer = setTimeout(saveNow, 800); show("쓰는 중…"); }
  var gone = false; // 상대가 메모를 지웠으면 더 저장하지 않는다
  // 연결이 잠깐 끊긴 것 같으면 5초 뒤 다시 저장
  function retryLater() {
    dirty = true;
    show("저장하지 못했어요. 잠시 뒤 다시 저장할게요");
    clearTimeout(timer);
    timer = setTimeout(saveNow, 5000);
  }
  function post(lines, keepalive, notify) {
    return fetch(editor.dataset.saveUrl, {
      method: "POST", credentials: "same-origin", keepalive: !!keepalive,
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ lines: lines, version: version, notify: !!notify }),
    });
  }
  // notify: 떠날 때의 마지막 저장이면 서버가 저장한 뒤 상대에게 알린다
  function saveNow(keepalive, notify) {
    clearTimeout(timer);
    if (!dirty || gone) return;
    var mine = serialize();
    // 떠날 때 보내는 요청은 크기 한도(64KB)가 있어 큰 글은 기기에만 남기고 다음에 연다
    if (keepalive && JSON.stringify(mine).length > 60000) { keepDraft(); return; }
    if (saving) {
      // 떠나는 중이면 기다리지 않고 지금 것을 보낸다 (안 되면 기기에 남긴 글로 다음에 안내)
      if (keepalive) post(mine, true, notify).catch(function () {});
      again = true;
      return;
    }
    saving = true; dirty = false;
    post(mine, keepalive, notify).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { status: r.status, data: d }; });
    }).then(function (res) {
      if (res.status === 200 && res.data.ok) {
        version = res.data.version; show("저장했어요");
        if (!dirty) clearDraft(); else keepDraft();
      } else if (res.status === 409) conflict(res.data);
      else if (res.status === 404) { gone = true; show("메모가 지워졌어요"); } // 쓴 글은 기기에 남겨 둔다
      else if (res.status === 400) { dirty = false; show(res.data.error || "저장하지 못했어요"); } // 너무 긴 글 등: 고쳐야 저장
      else retryLater();
    }).catch(retryLater)
      .then(function () { saving = false; if (again) { again = false; saveNow(); } });
  }
  // 상대가 먼저 고쳤으면: 새 내용을 보여 주고, 내 글은 복사할 수 있게 남긴다
  var mineText = "";
  function asText(lines) {
    return lines.map(function (l) { return (l.t === "check" ? (l.on ? "☑ " : "☐ ") : "") + l.s; }).join("\n");
  }
  function conflict(d) {
    var mineNow = serialize(); // 저장 중에 더 친 글까지
    version = d.version;
    mineText = asText(mineNow);
    render(d.lines || []);
    dirty = false;
    clearDraft();
    if (conflictBox) conflictBox.hidden = false;
    show("");
  }
  // ---------- 기기에 남기기: 떠나는 중 저장이 끊기거나 충돌해도 내 글을 잃지 않게 ----------
  var draftKey = "memo-draft:" + editor.dataset.saveUrl;
  function keepDraft() {
    try { localStorage.setItem(draftKey, JSON.stringify({ lines: serialize(), version: version })); } catch (e) { /* 저장소 없음 */ }
  }
  function clearDraft() { try { localStorage.removeItem(draftKey); } catch (e) { /* 괜찮다 */ } }
  // 줄 목록 비교 (서버 DB 가 JSON 키 순서를 바꿔도 같게 본다)
  function sameLines(a, b) {
    var key = function (ls) { return (ls || []).map(function (l) { return l.t + "|" + (l.on ? 1 : 0) + "|" + l.s; }).join("\n"); };
    return key(a) === key(b);
  }
  var copy = document.querySelector("[data-copy-mine]");
  if (copy) copy.addEventListener("click", function () {
    if (navigator.clipboard) navigator.clipboard.writeText(mineText).then(function () {
      copy.textContent = "복사했어요";
      setTimeout(function () { copy.textContent = "내 글 복사"; }, 2000);
    });
  });
  var closeConflict = document.querySelector("[data-conflict-close]");
  if (closeConflict) closeConflict.addEventListener("click", function () { conflictBox.hidden = true; });
  // 이번에 고친 게 있으면 떠날 때 한 번 상대에게 알린다 (서버가 30분에 한 번으로 거른다)
  var editedHere = false;
  function notifyPartner() {
    if (!editedHere || gone || !editor.dataset.notifyUrl) return;
    editedHere = false;
    fetch(editor.dataset.notifyUrl, { method: "POST", keepalive: true, credentials: "same-origin", headers: { "X-CSRFToken": csrf() } }).catch(function () {});
  }
  // 저장할 게 남았으면 알림을 그 저장에 실어 보낸다 (따로 보내면 저장보다 먼저 도착해 빈 제목으로 보일 수 있다)
  function leave() {
    if (dirty && !gone) {
      var notify = editedHere;
      editedHere = false;
      keepDraft();
      saveNow(true, notify);
    } else notifyPartner();
  }
  window.addEventListener("pagehide", leave);
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden") leave(); });

  render(data.lines || []);
  // 지난번에 저장하지 못한 내 글이 기기에 남아 있으면: 서버가 그대로면 이어서 저장, 그새 바뀌었으면 안내
  (function () {
    var draft = null;
    try { draft = JSON.parse(localStorage.getItem(draftKey) || "null"); } catch (e) { draft = null; }
    if (!draft || !draft.lines) return;
    if (sameLines(draft.lines, data.lines)) return clearDraft();
    if (draft.version === version) {
      render(draft.lines); dirty = true; schedule(); show("저장하지 못한 글을 이어서 저장해요");
    } else {
      mineText = asText(draft.lines);
      clearDraft();
      if (conflictBox) conflictBox.hidden = false;
    }
  })();
  // 새 메모(빈 첫 줄)면 바로 쓸 수 있게
  if (serialize().length === 1 && !serialize()[0].s) { editor.focus(); setCaret(0, 0); }
})();
