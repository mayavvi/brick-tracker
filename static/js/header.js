/**
 * Shared shell header: user identity, calendar, greeting, module menu.
 */
function headerApp() {
  let _prefsTimer = null;
  let _greetingTimer = null;

  function defaultPrefs() {
    return {
      selected_studies: [],
      selected_tracker_files: {},
      person_filter: "",
      role_filter: "all",
      time_range: "",
      search_query: "",
      show_charts: true,
    };
  }

  return {
    currentUser: null,
    prefsLoaded: false,
    _prefsSnapshot: null,
    showCalendar: false,
    calYear: new Date().getFullYear(),
    calMonth: new Date().getMonth(),
    todayStr: new Date().toLocaleDateString("zh-CN"),
    menuOpen: false,
    userMenuOpen: false,
    greeting: window.BrickGreetings ? window.BrickGreetings.pickFor(new Date().getHours()) : "",
    _greetingHour: new Date().getHours(),

    get calTitle() {
      return `${this.calYear}年${this.calMonth + 1}月`;
    },

    get calDays() {
      const year = this.calYear;
      const month = this.calMonth;
      const firstDay = new Date(year, month, 1);
      const lastDay = new Date(year, month + 1, 0);
      let startDow = firstDay.getDay();
      if (startDow === 0) startDow = 7;

      const today = new Date();
      const todayStr = `${today.getFullYear()}-${today.getMonth()}-${today.getDate()}`;
      const days = [];

      const prevMonth = new Date(year, month, 0);
      for (let i = startDow - 1; i >= 1; i--) {
        days.push({ day: prevMonth.getDate() - i + 1, other: true, today: false });
      }

      for (let d = 1; d <= lastDay.getDate(); d++) {
        const isToday = `${year}-${month}-${d}` === todayStr;
        days.push({ day: d, other: false, today: isToday });
      }

      const remaining = 42 - days.length;
      for (let d = 1; d <= remaining; d++) {
        days.push({ day: d, other: true, today: false });
      }

      return days;
    },

    calPrev() {
      if (this.calMonth === 0) {
        this.calMonth = 11;
        this.calYear--;
      } else {
        this.calMonth--;
      }
    },

    calNext() {
      if (this.calMonth === 11) {
        this.calMonth = 0;
        this.calYear++;
      } else {
        this.calMonth++;
      }
    },

    calToday() {
      const now = new Date();
      this.calYear = now.getFullYear();
      this.calMonth = now.getMonth();
    },

    get activeModule() {
      const p = (window.location.pathname || "").replace(/\/+$/, "");
      if (p.endsWith("/me")) return "me";
      if (p.endsWith("/file-compare")) return "file-compare";
      if (p.endsWith("/tracker")) return "tracker";
      return "welcome";
    },

    navUrl(path) {
      const b = typeof window.API_BASE !== "undefined" && window.API_BASE ? window.API_BASE : "";
      if (path === "/") {
        return b ? b + "/" : "/";
      }
      return b + path;
    },

    moduleItemClass(id) {
      const on = this.activeModule === id;
      return on
        ? "shell-module-item-active"
        : "text-stone-700 hover:bg-[#f4efe6]";
    },

    async init() {
      await this._loadUser();
      await this._loadPrefsSnapshot();
      this.prefsLoaded = true;
      this.$watch("greeting", (v) => this._typeGreeting(v));
      this.$nextTick(() => this._typeGreeting(this.greeting));
      this._startGreetingTimer();
    },

    _typeGreeting(text) {
      const el = document.getElementById("shell-greeting");
      if (!el) return;
      el.textContent = text || "";
    },

    _startGreetingTimer() {
      if (_greetingTimer) clearInterval(_greetingTimer);
      _greetingTimer = setInterval(() => {
        const h = new Date().getHours();
        if (h !== this._greetingHour && window.BrickGreetings) {
          this._greetingHour = h;
          this.greeting = window.BrickGreetings.pickFor(h);
        }
      }, 60000);
    },

    async _loadUser() {
      try {
        const resp = await fetch("/api/user/me");
        if (resp.status === 401 || resp.status === 403) {
          window.location.reload();
          return;
        }
        if (!resp.ok) throw new Error(String(resp.status));
        this.currentUser = await resp.json();
      } catch (e) {
        Alpine.store("toast").push("加载用户信息失败 " + e, "error");
        this.currentUser = { username: "unknown", display_name: "" };
      }
    },

    async _loadPrefsSnapshot() {
      try {
        const resp = await fetch("/api/user/preferences");
        if (!resp.ok) throw new Error("prefs");
        const prefs = await resp.json();
        this._prefsSnapshot = Object.assign(defaultPrefs(), prefs);
      } catch (_) {
        this._prefsSnapshot = defaultPrefs();
      }
    },
  };
}
