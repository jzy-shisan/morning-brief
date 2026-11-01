/* 外观 / 密度 / 领域切换 / 阅读进度 —— 首页与往期页共用同一套行为 */
(function () {
  var root = document.documentElement;
  var KEY = "fyb-share-theme";
  var DKEY = "fyb-share-density";
  var FKEY = "fyb-share-fs";
  var PRESETS = {
    paper: { "--bg": "#f6f4ef", "--surface": "#fffefb", "--fg": "#1c1a17", "--muted": "#6e6960", "--line": "rgba(28,26,23,.10)", "--accent": "#a8452a" },
    ink:   { "--bg": "#f2f4f6", "--surface": "#fbfcfd", "--fg": "#16202a", "--muted": "#65717d", "--line": "rgba(22,32,42,.10)", "--accent": "#2f5d8a" },
    moss:  { "--bg": "#f3f4ee", "--surface": "#fcfdf8", "--fg": "#1d2118", "--muted": "#5f6657", "--line": "rgba(29,33,24,.10)", "--accent": "#4d6141" },
    night: { "--bg": "#15161a", "--surface": "#1c1e23", "--fg": "#e8e6e1", "--muted": "#a3a29e", "--line": "rgba(232,230,225,.12)", "--accent": "#d98b5f" }
  };
  var VIEW = "all";
  var dens = "2";

  function each(list, fn) { Array.prototype.forEach.call(list, fn); }
  function setVars(vars) { if (vars) Object.keys(vars).forEach(function (k) { root.style.setProperty(k, vars[k]); }); }
  function lum(hex) {
    var m = /^#?([a-f\d]{2})([a-f\d]{2})([a-f\d]{2})$/i.exec(hex || "");
    if (!m) return 1;
    var r = parseInt(m[1], 16) / 255, g = parseInt(m[2], 16) / 255, b = parseInt(m[3], 16) / 255;
    return 0.2126 * r + 0.7152 * g + 0.0722 * b;
  }

  var api = {
    /* 渲染完正文后调用：接上面板、折叠、筛选、进度条 */
    init: function () {
      var sw = document.querySelectorAll(".swatch");
      var sz = document.querySelectorAll(".sizewrap button");
      var dn = document.querySelectorAll(".panel button[data-den]");
      var tabs = document.querySelectorAll(".tabs button");
      var panel = document.getElementById("panel");
      var tbtn = document.getElementById("tbtn");

      // ---- 配色 ----
      var saved = null;
      try { saved = JSON.parse(localStorage.getItem(KEY) || "null"); } catch (e) {}
      if (saved && saved.vars) setVars(saved.vars);
      var fs = null;
      try { fs = localStorage.getItem(FKEY); } catch (e) {}
      if (!fs && saved && saved.fs) fs = saved.fs;
      if (fs) root.style.setProperty("--fs", fs);

      function mark(p, size) {
        each(sw, function (b) { b.dataset.active = b.dataset.p === p ? "1" : "0"; });
        each(sz, function (b) { b.dataset.active = b.dataset.fs === size ? "1" : "0"; });
      }
      mark(saved && saved.p, fs);

      each(sw, function (b) {
        b.addEventListener("click", function () {
          var vars = PRESETS[b.dataset.p];
          setVars(vars);
          try { localStorage.setItem(KEY, JSON.stringify({ p: b.dataset.p, vars: vars })); } catch (e) {}
          try { localStorage.removeItem(KEY + "-bg"); } catch (e) {}
          mark(b.dataset.p, fs);
        });
      });
      each(sz, function (b) {
        b.addEventListener("click", function () {
          fs = b.dataset.fs;
          root.style.setProperty("--fs", fs);
          try { localStorage.setItem(FKEY, fs); } catch (e) {}
          mark(saved && saved.p, fs);
        });
      });

      // ---- 自定义背景色 ----
      var pick = document.getElementById("bgpick");
      var reset = document.getElementById("bgreset");
      function applyBg(hex) {
        var dark = lum(hex) < 0.45;
        setVars(dark
          ? { "--bg": hex, "--surface": "rgba(255,255,255,.05)", "--fg": "#f2ede4", "--muted": "#a7a099", "--line": "rgba(255,255,255,.14)", "--accent": "#d98b5f" }
          : { "--bg": hex, "--surface": "rgba(0,0,0,.03)", "--fg": "#1d1b18", "--muted": "#6e6960", "--line": "rgba(0,0,0,.13)", "--accent": "#a8452a" });
      }
      if (pick) {
        var savedBg = null;
        try { savedBg = localStorage.getItem(KEY + "-bg"); } catch (e) {}
        if (savedBg) { pick.value = savedBg; applyBg(savedBg); }
        pick.addEventListener("input", function () {
          applyBg(pick.value);
          try { localStorage.setItem(KEY + "-bg", pick.value); } catch (e) {}
          mark(null, fs);
        });
      }
      if (reset) {
        reset.addEventListener("click", function () {
          try { localStorage.removeItem(KEY + "-bg"); localStorage.removeItem(KEY); localStorage.removeItem(FKEY); } catch (e) {}
          location.reload();
        });
      }

      // ---- 面板开关 ----
      if (panel && /panel/.test(location.search)) panel.classList.add("open");
      if (tbtn && panel) {
        tbtn.setAttribute("aria-expanded", panel.classList.contains("open") ? "true" : "false");
        tbtn.addEventListener("click", function () {
          var open = panel.classList.toggle("open");
          tbtn.setAttribute("aria-expanded", open ? "true" : "false");
        });
      }

      // ---- 密度 + 领域筛选 ----
      try { dens = localStorage.getItem(DKEY) || "2"; } catch (e) {}
      if (["1", "2", "3"].indexOf(dens) < 0) dens = "2";

      function layout() {
        var total = 0;
        each(document.querySelectorAll("section.sec"), function (s) {
          var dom = s.getAttribute("data-dom");
          var inView = VIEW === "all" || !dom || dom === VIEW;
          s.classList.toggle("hidden-sec", !inView);
          if (!inView) return;
          var open = s.classList.contains("open");
          var arts = s.querySelectorAll("article"), shown = 0;
          each(arts, function (a) {
            var ord = parseInt(a.getAttribute("data-ord"), 10) || 1;
            var hide = !open && ord > parseInt(dens, 10);
            a.classList.toggle("hidden", hide);
            if (!hide) shown++;
          });
          total += shown;
          var btn = s.querySelector(".more button");
          if (btn) {
            var rest = arts.length - shown;
            if (rest > 0) { btn.style.display = ""; btn.textContent = "还有 " + rest + " 条 · 展开"; }
            else { btn.style.display = "none"; }
          }
        });
        var cnt = document.getElementById("cnt");
        if (cnt) cnt.textContent = total + " 条";
        var mins = document.getElementById("mins");
        if (mins) {
          var chars = 0;
          each(document.querySelectorAll("article:not(.hidden)"), function (a) {
            if (a.closest("section.hidden-sec")) return;
            chars += a.textContent.length;
          });
          mins.textContent = Math.max(1, Math.round(chars / 480));
        }
        each(dn, function (b) { b.dataset.active = b.dataset.den === dens ? "1" : "0"; });
        each(tabs, function (b) { b.dataset.active = b.getAttribute("data-view") === VIEW ? "1" : "0"; });
      }

      each(dn, function (b) {
        b.addEventListener("click", function () {
          dens = b.dataset.den;
          try { localStorage.setItem(DKEY, dens); } catch (e) {}
          layout();
        });
      });

      document.addEventListener("click", function (e) {
        var b = e.target.closest ? e.target.closest(".more button") : null;
        if (!b) return;
        var s = b.closest("section");
        if (s) { s.classList.add("open"); layout(); }
      });

      View.set = function (v) {
        VIEW = v;
        layout();
      };

      // ---- 领域切换 ----
      each(tabs, function (b) {
        b.addEventListener("click", function () {
          View.set(b.getAttribute("data-view"));
          window.scrollTo({ top: 0, behavior: "smooth" });
        });
      });

      layout();

      // ---- 阅读进度 ----
      var bar = document.getElementById("progress");
      if (bar) {
        var onScroll = function () {
          var h = document.documentElement.scrollHeight - window.innerHeight;
          bar.style.width = (h > 0 ? (window.scrollY / h) * 100 : 0) + "%";
        };
        window.addEventListener("scroll", onScroll, { passive: true });
        onScroll();
      }
    }
  };

  var View = { set: function () {} };
  window.FybTheme = api;
})();
