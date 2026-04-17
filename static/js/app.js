/**
 * Alpine.js application state for the tracker dashboard.
 */
const _API = (() => {
  // Primary: server-injected value from template
  if (typeof window.API_BASE === "string" && window.API_BASE !== "") return window.API_BASE;
  // Fallback: derive from this script's own URL (always correct if the script loaded)
  const src = document.currentScript && document.currentScript.src;
  if (src) {
    const path = new URL(src).pathname;
    const i = path.indexOf("/static/");
    if (i > 0) return path.substring(0, i);
  }
  return "";
})();

function trackerApp() {
  const STATUS_FILTERS = {
    total: () => true,
    in_progress: (t, role) => {
      if (role === "main") return !t.main_status;
      if (role === "qc") return !t.qc_status;
      return !t.main_status && !t.qc_status;
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

    // --- state ---
    searchQuery: "",
    studyList: [],
    selectedStudies: [],
    selectedTrackerFiles: {},
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
    greeting: (() => {
      const h = new Date().getHours();
      if (h < 9) return "早安~ 新的一天，元气满满！☀️";
      if (h < 12) return "上午好！冲一杯咖啡开始搬砖吧 ☕";
      if (h < 14) return "中午好！吃饱了才有力气干活 🍱";
      if (h < 18) return "下午好！续杯咖啡，继续肝 ☕";
      return "晚上好！今天辛苦啦~ 早点回家 🌙";
    })(),

    // --- custom tasks ---
    customTasks: [],
    showCustomTaskModal: false,
    editingCustomTask: null,
    customTaskForm: { study_id: "", task_name: "", description: "", main_person: "", main_status: "", qc_person: "", qc_status: "", ddl: "", tags: "" },

    // --- lifecycle ---
    async init() {
      await this._loadUser();
      await this._restorePreferences();

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
    },

    // --- user identity ---
    async _loadUser() {
      try {
        const resp = await fetch(_API + "/api/user/me");
        this.currentUser = await resp.json();
      } catch (e) {
        console.error("Failed to load user:", e);
        this.currentUser = { username: "unknown", display_name: "" };
      }
    },

    // --- preferences ---
    async _restorePreferences() {
      try {
        const resp = await fetch(_API + "/api/user/preferences");
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
        this.prefsLoaded = true;
      } catch (e) {
        console.error("Failed to restore preferences:", e);
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
      };
      try {
        await fetch(_API + "/api/user/preferences", {
          method: "PUT",
          headers: { "Content-Type": "application/json" },
          body: JSON.stringify(payload),
        });
      } catch (e) {
        console.error("Failed to save preferences:", e);
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
      } else {
        delete this.selectedTrackerFiles[sid];
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
        await fetch(_API + "/api/cache/refresh", { method: "POST" });
        if (this.searchQuery.trim().length > 0) {
          await this.searchStudies();
        }
      } catch (e) {
        console.error("Cache refresh failed:", e);
      } finally {
        this.refreshingCache = false;
      }
    },

    // --- methods ---
    async searchStudies() {
      const q = this.searchQuery.trim();
      if (q.length < 1) {
        this.studyList = [];
        return;
      }
      this.loadingStudies = true;
      try {
        const resp = await fetch(`${_API}/api/studies/search?q=${encodeURIComponent(q)}`);
        this.studyList = await resp.json();
      } catch (e) {
        console.error("Search failed:", e);
        this.studyList = [];
      } finally {
        this.loadingStudies = false;
      }
    },

    async loadDashboard() {
      if (this.selectedStudies.length === 0) return;
      this.loadingDashboard = true;
      try {
        const pUrl = `${_API}/api/persons?${this.selectedStudies.map((s) => `study_ids=${encodeURIComponent(s)}`).join("&")}`;
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
        const dResp = await fetch(_API + "/api/dashboard", {
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
      } catch (e) {
        console.error("Dashboard load failed:", e);
      } finally {
        this.loadingDashboard = false;
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
        const resp = await fetch(_API + "/api/custom-tasks");
        this.customTasks = await resp.json();
      } catch (e) {
        console.error("Failed to load custom tasks:", e);
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
      if (!this.customTaskForm.ddl) {
        alert("别忘了填死线呀~ 没有 deadline 的活等于没有活（不是）");
        return;
      }
      const payload = {
        ...this.customTaskForm,
        tags: this.customTaskForm.tags ? this.customTaskForm.tags.split(",").map((s) => s.trim()).filter(Boolean) : [],
        ddl: this.customTaskForm.ddl,
      };
      try {
        if (this.editingCustomTask) {
          await fetch(`${_API}/api/custom-tasks/${this.editingCustomTask}`, {
            method: "PUT",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
        } else {
          await fetch(_API + "/api/custom-tasks", {
            method: "POST",
            headers: { "Content-Type": "application/json" },
            body: JSON.stringify(payload),
          });
        }
        this.showCustomTaskModal = false;
        await this._loadCustomTasks();
      } catch (e) {
        console.error("Failed to save custom task:", e);
      }
    },

    async deleteCustomTask(taskId) {
      if (!confirm("真的要扔掉这个活儿吗？(つ﹏⊂) 扔了就捡不回来了哦~")) return;
      try {
        await fetch(`${_API}/api/custom-tasks/${taskId}`, { method: "DELETE" });
        await this._loadCustomTasks();
      } catch (e) {
        console.error("Failed to delete custom task:", e);
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
        关闭问题: "bg-emerald-100 text-emerald-700",
        "已完成，可以QC": "bg-sky-100 text-sky-700",
        进行中: "bg-amber-100 text-amber-700",
        "有问题，请修改": "bg-rose-100 text-rose-700",
        "待定，请留意": "bg-stone-100 text-stone-500",
      };
      return m[status] || "bg-stone-50 text-stone-400";
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
      if (days < 0) return "bg-red-50";
      if (days <= 3) return "bg-red-50";
      if (days <= 5) return "bg-orange-50";
      if (days <= 10) return "bg-yellow-50";
      return "";
    },

    ddlTextClass(task) {
      const days = this._ddlDaysLeft(task);
      if (days === null) return "text-gray-400";
      if (days < 0) return "text-red-600 font-bold";
      if (days <= 3) return "text-red-600 font-semibold";
      if (days <= 5) return "text-orange-500 font-semibold";
      if (days <= 10) return "text-yellow-600";
      return "text-gray-500";
    },
  };
}
