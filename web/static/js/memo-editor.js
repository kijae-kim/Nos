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
  function changed() { dirty = true; schedule(); }
  function splitAtCaret() {
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

  editor.addEventListener("beforeinput", function (e) {
    if (e.inputType === "insertParagraph" || e.inputType === "insertLineBreak") {
      e.preventDefault(); splitAtCaret();
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
  editor.addEventListener("input", function () {
    // 줄 밖 글·겹친 줄이 생기면 정리 (커서 자리 유지)
    var messy = Array.prototype.some.call(editor.childNodes, function (n) {
      return n.nodeType === 3 || (n.nodeType === 1 && (!n.classList.contains("ln") || n.querySelector("div,p,span,b,i,font")));
    });
    if (messy || !editor.childNodes.length) {
      var c = caret();
      render(serialize());
      if (c) setCaret(c.line, c.offset);
    }
    changed();
  });
  // 줄 왼쪽 동그라미를 누르면 체크 (커서는 옮기지 않는다)
  editor.addEventListener("mousedown", function (e) {
    var line = e.target.closest && e.target.closest(".ln.todo");
    if (!line || e.clientX - line.getBoundingClientRect().left > TICK) return;
    e.preventDefault();
    line.classList.toggle("on");
    changed();
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
  function saveNow(keepalive) {
    clearTimeout(timer);
    if (!dirty) return;
    if (saving) { again = true; return; } // 한 번에 하나, 끝난 뒤 최신 것만
    saving = true; dirty = false;
    var mine = serialize();
    fetch(editor.dataset.saveUrl, {
      method: "POST", credentials: "same-origin", keepalive: !!keepalive,
      headers: { "Content-Type": "application/json", "X-CSRFToken": csrf() },
      body: JSON.stringify({ lines: mine, version: version }),
    }).then(function (r) {
      return r.json().catch(function () { return {}; }).then(function (d) { return { status: r.status, data: d }; });
    }).then(function (res) {
      if (res.status === 200 && res.data.ok) { version = res.data.version; show("저장했어요"); }
      else if (res.status === 409) conflict(res.data, mine);
      else { dirty = true; show("저장하지 못했어요. 잠시 뒤 다시 할게요"); }
    }).catch(function () { dirty = true; show("저장하지 못했어요. 잠시 뒤 다시 할게요"); })
      .then(function () { saving = false; if (again) { again = false; saveNow(); } });
  }
  // 상대가 먼저 고쳤으면: 새 내용을 보여 주고, 내 글은 복사할 수 있게 남긴다
  var mineText = "";
  function conflict(d, mine) {
    version = d.version;
    mineText = mine.map(function (l) { return (l.t === "check" ? (l.on ? "☑ " : "☐ ") : "") + l.s; }).join("\n");
    render(d.lines || []);
    dirty = false;
    if (conflictBox) conflictBox.hidden = false;
    show("");
  }
  var copy = document.querySelector("[data-copy-mine]");
  if (copy) copy.addEventListener("click", function () {
    if (navigator.clipboard) navigator.clipboard.writeText(mineText).then(function () { copy.textContent = "복사했어요"; });
  });
  window.addEventListener("pagehide", function () { if (dirty) saveNow(true); });
  document.addEventListener("visibilitychange", function () { if (document.visibilityState === "hidden" && dirty) saveNow(true); });

  render(data.lines || []);
  // 새 메모(빈 첫 줄)면 바로 쓸 수 있게
  if (serialize().length === 1 && !serialize()[0].s) { editor.focus(); setCaret(0, 0); }
})();
