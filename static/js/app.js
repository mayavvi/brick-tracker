/**
 * Alpine.js application state for the tracker dashboard.
 */
function trackerApp() {
  // Keyboard shortcuts wired to the app instance (set in init)
  let _keyHandler = null;
  const STATUS_FILTERS = {
    total: () => true,
    in_progress: (t, role) => {
      if (role === "main") return !t.main_status;
      if (role === "qc") return !t.qc_status;
      return !t.main_status || !t.qc_status;
    },
    completed_ready_qc: (t) => t.main_status === "已完成，可以QC",
    has_issues: (t) => t.qc_status === "有问题，请修改",
    pending: (t) => t.qc_status === "待定，请留意",
    closed: (t) => t.qc_status === "关闭问题",
  };

  let _prefsSaveTimer = null;

  return {
    // --- user ---
    currentUser: null,
    prefsLoaded: false,

    // --- theme & charts ---
    showCharts: true,
    chartsReady: false,

    // --- state ---
    searchQuery: "",
    studyList: [],
    selectedStudies: [],
    selectedTrackerFiles: {},
    _studyCache: {},
    personList: [],
    personFilter: "",
    roleFilter: "all",
    timeRange: "",
    statusFilter: "",
    loadingStudies: false,
    loadingDashboard: false,
    refreshingCache: false,
    dashboardLoaded: false,
    summary: {
      total: 0,
      in_progress: 0,
      completed_ready_qc: 0,
      has_issues: 0,
      pending: 0,
      closed: 0,
      not_started: 0,
    },
    _baseSummary: null,
    allTasks: [],
    tasks: [],
    taskGroups: [],
    sidebarOpen: true,
    sidebarCollapsing: false,
    animationKey: 0,
    todayStr: new Date().toLocaleDateString("zh-CN"),
    greeting: (window.BrickGreetings ? window.BrickGreetings.pickFor(new Date().getHours()) : ""),
    _greetingHour: new Date().getHours(),
    _greetingTimer: null,

    // --- custom tasks ---
    customTasks: [],
    showCustomTaskModal: false,
    editingCustomTask: null,
    customTaskForm: { study_id: "", task_name: "", description: "", main_person: "", main_status: "", qc_person: "", qc_status: "", ddl: "", tags: "" },

    // --- lifecycle ---
    async init() {
      await this._loadUser();
      await this._restorePreferences();
      this._setupKeyboard();

      this.$watch("personFilter", () => {
        if (this.dashboardLoaded) this.loadDashboard();
        this._scheduleSavePrefs();
      });
      this.$watch("roleFilter", () => {
        if (this.dashboardLoaded) this.loadDashboard();
        this._scheduleSavePrefs();
      });
      this.$watch("timeRange", () => {
        if (this.dashboardLoaded) this.loadDashboard();
        this._scheduleSavePrefs();
      });
      this.$watch("statusFilter", () => {
        if (this.dashboardLoaded) this._applyStatusFilter();
      });

      await this._loadCustomTasks();

      if (this.selectedStudies.length > 0) {
        await this.searchStudies();
        await this.loadDashboard();
      }

      this._startGreetingTimer();
    },

    _startGreetingTimer() {
      if (this._greetingTimer) clearInterval(this._greetingTimer);
      this._greetingTimer = setInterval(() => {
        const h = new Date().getHours();
        if (h !== this._greetingHour && window.BrickGreetings) {
          this._greetingHour = h;
          this.greeting = window.BrickGreetings.pickFor(h);
        }
      }, 60000);
    },

    _setupKeyboard() {
      var self = this;
      var gPressed = false, gTimer = null;
      document.addEventListener('keydown', function(e) {
        // Skip when focus is in an input/select/textarea
        var tag = (document.activeElement || {}).tagName;
        if (tag === 'INPUT' || tag === 'SELECT' || tag === 'TEXTAREA') {
          if (e.key === 'Escape') { document.activeElement.blur(); }
          return;
        }
        if (e.key === '/') {
          e.preventDefault();
          var el = document.getElementById('study-search-input');
          if (el) el.focus();
        } else if (e.key === 'r' && !e.ctrlKey && !e.metaKey) {
          self.refreshProjectList();
        } else if (e.key === 'd' && !e.ctrlKey && !e.metaKey) {
          Alpine.store('theme').toggle();
          self._scheduleSavePrefs();
        } else if (e.key === 'g') {
          gPressed = true;
          clearTimeout(gTimer);
          gTimer = setTimeout(function() { gPressed = false; }, 800);
        } else if (e.key === 'm' && gPressed) {
          window.location.href = '/me';
        }
      });
    },

    // --- user identity ---
    async _loadUser() {
      try {
        const resp = await fetch("/api/user/me");
        if (!resp.ok) throw new Error(resp.status);
        this.currentUser = await resp.json();
      } catch (e) {
        Alpine.store('toast').push("加载用户信息失败 " + e, "error");
        this.currentUser = { username: "unknown", display_name: "" };
      }
    },

    // --- preferences ---
    async _restorePreferences() {
      try {
        const resp = await fetch("/api/user/preferences");
        const prefs = await resp.json();
        if (prefs.selected_studies && prefs.selected_studies.length > 0) {
          this.selectedStudies = prefs.selected_studies;
        }
        if (prefs.selected_tracker_files) {
          this.selectedTrackerFiles = prefs.selected_tracker_files;
        }
        if (prefs.person_filter) this.personFilter = prefs.person_filter;
        if (prefs.role_filter) this.roleFilter = prefs.role_filter;
        if (prefs.time_range) this.timeRange = prefs.time_range;
        if (prefs.search_query) this.searchQuery = prefs.search_query;
        if (typeof prefs.show_charts === 'boolean') this.showCharts = prefs.show_charts;
        // Apply saved theme (server-side prefs override localStorage as source-of-truth)
        if (prefs.theme === 'dark' || prefs.theme === 'light') {
          const wantDark = prefs.theme === 'dark';
          document.documentElement.classList.toggle('dark', wantDark);
          localStorage.setItem('brick-theme', prefs.theme);
          Alpine.store('theme').dark = wantDark;
        }
        this.prefsLoaded = true;
      } catch (e) {
        this.prefsLoaded = true;
      }
    },

    _scheduleSavePrefs() {
      if (_prefsSaveTimer) clearTimeout(_prefsSaveTimer);
      _prefsSaveTimer = setTimeout(() => this._savePreferences(), 500);
    },

    async _savePreferences() {
      if (!this.prefsLoaded) return;
      const payload = {
        selected_studies: this.selectedStudies,
        selected_tracker_files: this.selectedTrackerFiles,
        person_filter: this.personFilter,
        role_filter: this.roleFilter,
        time_range: this.timeRange,
        search_query: this.searchQuery,
        theme: Alpine.store('theme').dark ? 'dark' : 'light',
        show_charts: this.showCharts,
      };
      try {
        await fetch("/api/user/preferences", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } catch (_) {
        // Silently ignore preference save failures to avoid toast spam
      }
    },

    // --- status card filter ---
    setStatusFilter(key) {
      this.statusFilter = this.statusFilter === key ? "" : key;
    },

    _applyStatusFilter() {
      let filtered = this.allTasks;
      if (this.statusFilter && STATUS_FILTERS[this.statusFilter]) {
        filtered = filtered.filter((t) => STATUS_FILTERS[this.statusFilter](t, this.roleFilter));
      }
      this.tasks = filtered;
      this.taskGroups = this._groupTasks(filtered);
      this.animationKey++;
    },

    // --- sidebar ---
    toggleSidebar() {
      this.sidebarCollapsing = true;
      this.sidebarOpen = !this.sidebarOpen;
      setTimeout(() => { this.sidebarCollapsing = false; }, 350);
    },

    // --- tracker file selection ---
    onStudyToggle(study) {
      const sid = study.study_id;
      if (this.selectedStudies.includes(sid)) {
        this.selectedTrackerFiles[sid] = study.tracker_files.map((tf) => tf.file_path);
        this._studyCache[sid] = study;
      } else {
        delete this.selectedTrackerFiles[sid];
        delete this._studyCache[sid];
      }
      this._scheduleSavePrefs();
    },

    toggleTrackerFile(studyId, filePath) {
      if (!this.selectedStudies.includes(studyId)) return;
      const arr = this.selectedTrackerFiles[studyId] || [];
      const idx = arr.indexOf(filePath);
      if (idx >= 0) {
        arr.splice(idx, 1);
      } else {
        arr.push(filePath);
      }
      this.selectedTrackerFiles[studyId] = [...arr];
      this._scheduleSavePrefs();
    },

    isTrackerSelected(studyId, filePath) {
      if (!this.selectedStudies.includes(studyId)) return false;
      const arr = this.selectedTrackerFiles[studyId];
      return arr && arr.includes(filePath);
    },

    _getSelectedFilePaths() {
      const paths = [];
      for (const sid of this.selectedStudies) {
        const arr = this.selectedTrackerFiles[sid];
        if (arr) paths.push(...arr);
      }
      return paths;
    },

    // --- cache refresh ---
    async refreshProjectList() {
      this.refreshingCache = true;
      try {
        const resp = await fetch("/api/cache/refresh", { method: "POST" });
        if (!resp.ok) throw new Error(resp.status);
        Alpine.store('toast').push("缓存已刷新，正在重新加载~", "success");
        if (this.searchQuery.trim().length > 0) {
          await this.searchStudies();
        }
      } catch (e) {
        Alpine.store('toast').push("刷新失败：" + e, "error");
      } finally {
        this.refreshingCache = false;
      }
    },

    // --- methods ---
    async searchStudies() {
      const q = this.searchQuery.trim();
      if (q.length < 2) {
        this.studyList = [];
        this._mergeSelectedIntoList();
        return;
      }
      this.loadingStudies = true;
      try {
        const resp = await fetch(`/api/studies/search?q=${encodeURIComponent(q)}`);
        if (!resp.ok) throw new Error(resp.status);
        this.studyList = await resp.json();
        for (const s of this.studyList) {
          if (this.selectedStudies.includes(s.study_id)) {
            this._studyCache[s.study_id] = s;
          }
        }
      } catch (e) {
        Alpine.store('toast').push("搜索出错了：" + e, "error");
        this.studyList = [];
      } finally {
        this.loadingStudies = false;
      }
      this._mergeSelectedIntoList();
    },

    _mergeSelectedIntoList() {
      const inList = new Set(this.studyList.map((s) => s.study_id));
      for (const sid of this.selectedStudies) {
        if (!inList.has(sid)) {
          this.studyList.push(
            this._studyCache[sid] || { compound: "", study_id: sid, tracker_files: [] }
          );
        }
      }
    },

    async loadDashboard() {
      if (this.selectedStudies.length === 0) return;
      this.loadingDashboard = true;
      try {
        const pUrl = `/api/persons?${this.selectedStudies.map((s) => `study_ids=${encodeURIComponent(s)}`).join("&")}`;
        const pResp = await fetch(pUrl);
        this.personList = await pResp.json();

        const trackerPaths = this._getSelectedFilePaths();
        const body = {
          study_ids: this.selectedStudies,
          tracker_file_paths: trackerPaths.length > 0 ? trackerPaths : null,
          person_name: this.personFilter || null,
          time_range: this.timeRange || null,
          role: this.roleFilter,
        };
        const dResp = await fetch("/api/dashboard", {
          method: "POST",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(body),
        });
        const data = await dResp.json();
        this._baseSummary = { ...data.summary };
        this.summary = data.summary;
        this.allTasks = data.tasks;
        this.statusFilter = "";
        this.tasks = data.tasks;
        this.taskGroups = this._groupTasks(data.tasks);
        this.dashboardLoaded = true;
        this.animationKey++;
        await this._loadCustomTasks();
        // Render charts after data is loaded
        this.$nextTick(() => { this._renderCharts(); });
      } catch (e) {
        Alpine.store('toast').push("加载看板失败：" + e, "error");
      } finally {
        this.loadingDashboard = false;
      }
    },

    _renderCharts() {
      if (!this.showCharts || typeof TrackerCharts === 'undefined') return;
      TrackerCharts.initDonut('chart-donut', this.summary);
      TrackerCharts.initBar('chart-bar', this.allTasks);
      TrackerCharts.initTimeline('chart-timeline', this.allTasks);
      this.chartsReady = true;
    },

    toggleCharts() {
      this.showCharts = !this.showCharts;
      this._scheduleSavePrefs();
      if (this.showCharts && this.dashboardLoaded) {
        this.$nextTick(() => { this._renderCharts(); });
      }
    },

    _groupTasks(tasks) {
      const studyMap = new Map();
      for (const t of tasks) {
        if (!studyMap.has(t.study_id)) {
          studyMap.set(t.study_id, { studyId: t.study_id, open: true, purposes: new Map() });
        }
        const studyNode = studyMap.get(t.study_id);
        if (!studyNode.purposes.has(t.task_purpose)) {
          studyNode.purposes.set(t.task_purpose, { purpose: t.task_purpose, open: true, sheets: new Map() });
        }
        const purposeNode = studyNode.purposes.get(t.task_purpose);
        if (!purposeNode.sheets.has(t.sheet_type)) {
          purposeNode.sheets.set(t.sheet_type, { sheetType: t.sheet_type, open: true, tasks: [] });
        }
        purposeNode.sheets.get(t.sheet_type).tasks.push(t);
      }
      const result = [];
      for (const [, studyNode] of studyMap) {
        const purposes = [];
        for (const [, pNode] of studyNode.purposes) {
          const sheets = Array.from(pNode.sheets.values());
          purposes.push({ purpose: pNode.purpose, open: true, sheets, taskCount: sheets.reduce((s, sh) => s + sh.tasks.length, 0) });
        }
        const totalCount = purposes.reduce((s, p) => s + p.taskCount, 0);
        result.push({ studyId: studyNode.studyId, open: true, purposes, taskCount: totalCount });
      }
      return result;
    },

    // --- custom tasks CRUD ---
    async _loadCustomTasks() {
      try {
        const resp = await fetch("/api/custom-tasks");
        if (!resp.ok) throw new Error(resp.status);
        this.customTasks = await resp.json();
      } catch (e) {
        Alpine.store('toast').push("加载自定义任务失败：" + e, "error");
      }
      this._refreshSummaryWithCustomTasks();
    },

    _refreshSummaryWithCustomTasks() {
      if (!this._baseSummary) return;
      const STATUS_MAP = {
        "进行中": "in_progress",
        "已完成，可以QC": "completed_ready_qc",
        "有问题，请修改": "has_issues",
        "待定，请留意": "pending",
        "关闭问题": "closed",
      };
      const s = { ...this._baseSummary };
      for (const ct of this.customTasks) {
        s.total++;
        let sideStatus;
        if (this.roleFilter === "main") sideStatus = ct.main_status;
        else if (this.roleFilter === "qc") sideStatus = ct.qc_status;
        else sideStatus = ct.main_status || ct.qc_status;

        if (!sideStatus) {
          s.in_progress++;
          continue;
        }
        const mainKey = STATUS_MAP[sideStatus] || "";
        if (mainKey === "completed_ready_qc") s.completed_ready_qc++;
        if (mainKey === "in_progress") s.in_progress++;

        const qcKey = STATUS_MAP[ct.qc_status] || "";
        if (qcKey === "has_issues") s.has_issues++;
        else if (qcKey === "pending") s.pending++;
        else if (qcKey === "closed") s.closed++;
      }
      this.summary = s;
    },

    getCustomTasksForStudy(studyId) {
      return this.customTasks.filter((ct) => ct.study_id === studyId);
    },

    get customProjectGroups() {
      const map = new Map();
      for (const ct of this.customTasks) {
        if (!map.has(ct.study_id)) map.set(ct.study_id, []);
        map.get(ct.study_id).push(ct);
      }
      return Array.from(map.entries()).map(([sid, tasks]) => ({ studyId: sid, tasks, open: true }));
    },

    _taskNamePresets: ["MDR", "PD", "Ad-hoc request", "DSUR", "Meeting support", "MM request"],

    openAddCustomTask(studyId) {
      this.editingCustomTask = null;
      const defaultPerson = this.personFilter || "";
      this.customTaskForm = {
        study_id: studyId || "",
        task_name: "",
        description: "",
        main_person: defaultPerson,
        main_status: "进行中",
        qc_person: "",
        qc_status: "",
        ddl: "",
        tags: "",
      };
      this.showCustomTaskModal = true;
    },

    openEditCustomTask(ct) {
      this.editingCustomTask = ct.id;
      this.customTaskForm = {
        study_id: ct.study_id,
        task_name: ct.task_name,
        description: ct.description || "",
        main_person: ct.main_person || "",
        main_status: ct.main_status || "",
        qc_person: ct.qc_person || "",
        qc_status: ct.qc_status || "",
        ddl: ct.ddl || "",
        tags: (ct.tags || []).join(", "),
      };
      this.showCustomTaskModal = true;
    },

    async saveCustomTask() {
      // Validate required fields
      if (!this.customTaskForm.study_id.trim() || !this.customTaskForm.task_name.trim() || !this.customTaskForm.ddl) {
        Alpine.store('toast').push("项目名、活儿名和死线都是必填的哦~", "warning");
        return;
      }
      const payload = {
        ...this.customTaskForm,
        tags: this.customTaskForm.tags ? this.customTaskForm.tags.split(",").map((s) => s.trim()).filter(Boolean) : [],
        ddl: this.customTaskForm.ddl,
      };
      try {
        let resp;
        if (this.editingCustomTask) {
          resp = await fetch(`/api/custom-tasks/${this.editingCustomTask}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
        } else {
          resp = await fetch("/api/custom-tasks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
        }
        if (!resp.ok) throw new Error(resp.status);
        this.showCustomTaskModal = false;
        Alpine.store('toast').push(this.editingCustomTask ? "改好了！" : "加上了！冲！", "success");
        await this._loadCustomTasks();
      } catch (e) {
        Alpine.store('toast').push("保存失败：" + e, "error");
      }
    },

    async deleteCustomTask(taskId) {
      const ok = await Alpine.store('confirm').ask("真的要扔掉这个活儿吗？(つ﹏⊂) 扔了就捡不回来了哦~");
      if (!ok) return;
      try {
        const resp = await fetch(`/api/custom-tasks/${taskId}`, { method: "DELETE" });
        if (!resp.ok) throw new Error(resp.status);
        Alpine.store('toast').push("活儿扔了，轻装上阵！", "success");
        await this._loadCustomTasks();
      } catch (e) {
        Alpine.store('toast').push("删除失败：" + e, "error");
      }
    },

    // --- calendar ---
    showCalendar: false,
    calYear: new Date().getFullYear(),
    calMonth: new Date().getMonth(),

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

    // --- UI helpers ---
    statusBadge(status) {
      const m = {
        关闭问题: "bg-emerald-50 text-emerald-700 ring-1 ring-emerald-200/70 dark:bg-emerald-900/30 dark:text-emerald-300 dark:ring-emerald-800/60",
        "已完成，可以QC": "bg-sky-50 text-sky-700 ring-1 ring-sky-200/70 dark:bg-sky-900/30 dark:text-sky-300 dark:ring-sky-800/60",
        进行中: "bg-amber-50 text-amber-700 ring-1 ring-amber-200/70 dark:bg-amber-900/30 dark:text-amber-300 dark:ring-amber-800/60",
        "有问题，请修改": "bg-rose-50 text-rose-700 ring-1 ring-rose-200/70 dark:bg-rose-900/30 dark:text-rose-300 dark:ring-rose-800/60",
        "待定，请留意": "bg-stone-100 text-stone-600 ring-1 ring-stone-200/70 dark:bg-stone-800 dark:text-stone-300 dark:ring-stone-700",
      };
      return m[status] || "bg-stone-50 text-stone-400 ring-1 ring-stone-200/70 dark:bg-stone-800/60 dark:text-stone-500 dark:ring-stone-700";
    },

    _ddlDaysLeft(task) {
      if (!task.ddl) return null;
      const d = new Date(task.ddl);
      const now = new Date();
      now.setHours(0, 0, 0, 0);
      return Math.ceil((d - now) / 86400000);
    },

    ddlUrgencyClass(task) {
      const days = this._ddlDaysLeft(task);
      if (days === null) return "";
      if (days < 0) return "ddl-overdue";
      if (days <= 3) return "ddl-urgent";
      if (days <= 10) return "ddl-soon";
      return "";
    },

    ddlTextClass(task) {
      const days = this._ddlDaysLeft(task);
      if (days === null) return "text-stone-400 dark:text-stone-600";
      if (days < 0) return "text-rose-600 dark:text-rose-400 font-semibold";
      if (days <= 3) return "text-rose-600 dark:text-rose-400 font-semibold";
      if (days <= 5) return "text-amber-600 dark:text-amber-400 font-medium";
      if (days <= 10) return "text-amber-700 dark:text-amber-500";
      return "text-stone-500 dark:text-stone-400";
    },
  };
}
